from datetime import date

from janis_bioinformatics.data_types import BamBai, FastaFai
from janis_bioinformatics.tools import BioinformaticsWorkflow
from janis_bioinformatics.tools.bcftools import BcfToolsNormLatest as BcfToolsNorm
from janis_bioinformatics.tools.dawson import (
    CallSomaticFreeBayes_0_1 as CallSomaticFreeBayes,
)
from janis_bioinformatics.tools.dawson.createcallregions.base import CreateCallRegions
from janis_bioinformatics.tools.freebayes.versions import FreeBayes_1_3 as FreeBayes
from janis_bioinformatics.tools.htslib import BGZipLatest as BGZip, TabixLatest as Tabix
from janis_bioinformatics.tools.vcflib import (
    VcfAllelicPrimitivesLatest as VcfAllelicPrimitives,
    VcfCombineLatest as VcfCombine,
    VcfFixUpLatest as VcfFixUp,
    VcfStreamSortLatest as VcfStreamSort,
    VcfUniqAllelesLatest as VcfUniqAlleles,
    VcfUniqLatest as VcfUniq,
)
from janis_core import Array, Int, String


class FreeBayesSomaticWorkflow(BioinformaticsWorkflow):
    def id(self):
        return "FreeBayesSomaticWorkflow"

    def friendly_name(self):
        return "Freebayes somatic workflow"

    def tool_provider(self):
        return "Dawson Labs"

    def version(self):
        return "0.2"

    def bind_metadata(self):
        self.metadata.version = "0.2"
        self.metadata.dateCreated = date(2019, 10, 18)
        self.metadata.dateUpdated = date(2020, 12, 10)

        self.contributors = ["Sebastian Hollizeck"]
        self.metadata.keywords = [
            "variants",
            "freebayes",
            "variant caller",
            "multi sample",
        ]
        self.metadata.documentation = """
        This workflow uses the capabilities of freebayes to output all variants independent of the
        diploid model which then in turn allows us to create a likelihood based difference between
        the normal sample and an arbitrary amount of samples.
        This allows a joint somatic genotyping of multiple samples of the same individual.
                """.strip()

    def constructor(self):

        self.input("bams", Array(BamBai))

        self.input("reference", FastaFai)
        self.input("regionSize", int, default=10000000)

        self.input("normalSample", String)

        # this is the coverage per sample that is the max we will analyse. It will automatically
        # multiplied by the amount of input bams we get
        self.input("skipCov", Int(optional=True), default=500)

        # the same is true for min cov
        self.input("minCov", Int(optional=True), default=10)

        # this should be a conditional (if the callregions are supplied we use them, otherwise we
        # create them)
        self.step(
            "createCallRegions",
            CreateCallRegions(
                reference=self.reference, regionSize=self.regionSize, equalize=True
            ),
        )

        self.step(
            "callVariants",
            FreeBayes(
                bams=self.bams,
                reference=self.reference,
                pooledDiscreteFlag=True,
                gtQuals=True,
                strictFlag=True,
                pooledContinousFlag=True,
                reportMaxGLFlag=True,
                noABPriorsFlag=True,
                maxNumOfAlleles=4,
                noPartObsFlag=True,
                region=self.createCallRegions.regions,
                # here we multiply the skipCov input by the amount of input that we have
                skipCov=(self.skipCov * self.bams.length()),
                # things that are actually default, but janis does not recognize yet
                useDupFlag=False,
                minBaseQual=1,
                minSupMQsum=0,
                minSupQsum=0,
                minCov=self.minCov,
                # now here we are trying to play with the detection limits
                # we set the fraction to be very low, to include ALL of the sites in a potential analysis
                minAltFrac=0.01,
                # and we want at least one sample that has two high quality variants OR multiple
                # lower quality ones
                minAltQSum=70,
                # but we also want to have at least two reads overall with that variants
                # we do not care if they are between samples or if they are in the same sample, but
                # 2 is better than one
                minAltTotal=2,
            ),
            scatter="region",
        )
        # might actually rewrite this once everything works, to not combine the files here, but do
        # all of it scattered and then only combine the final output
        # self.step("combineRegions", VcfCombine(vcf=self.callVariants.out))

        #

        # self.step("compressAll", BGZip(file=self.sortAll.out))
        # self.step("indexAll", Tabix(file=self.compressAll.out))

        self.step(
            "callSomatic",
            CallSomaticFreeBayes(
                vcf=self.callVariants.out, normalSampleName=self.normalSample
            ),
            # added for parallel
            scatter="vcf",
        )

        self.step("combineRegions", VcfCombine(vcf=self.callSomatic.out))

        # should not be necessary here, but just to be save
        self.step(
            "sortSomatic1",
            VcfStreamSort(vcf=self.combineRegions.out, inMemoryFlag=True),
        )

        # no need to compress this here if it leads to problems when we dont have an index for the allelic allelicPrimitves
        self.step(
            "normalizeSomatic1",
            BcfToolsNorm(
                vcf=self.sortSomatic1.out,
                reference=self.reference,
                outputType="v",
                outputFilename="normalised.vcf",
            ),
        )

        self.step(
            "allelicPrimitves",
            VcfAllelicPrimitives(
                vcf=self.normalizeSomatic1.out,
                tagParsed="DECOMPOSED",
                keepGenoFlag=True,
            ),
        )

        self.step("fixSplitLines", VcfFixUp(vcf=self.allelicPrimitves.out))

        self.step(
            "sortSomatic2", VcfStreamSort(vcf=self.fixSplitLines.out, inMemoryFlag=True)
        )

        self.step(
            "normalizeSomatic2",
            BcfToolsNorm(
                vcf=self.sortSomatic2.out,
                reference=self.reference,
                outputType="v",
                outputFilename="normalised.vcf",
            ),
        )

        self.step("uniqueAlleles", VcfUniqAlleles(vcf=self.normalizeSomatic2.out))

        self.step(
            "sortFinal", VcfStreamSort(vcf=self.uniqueAlleles.out, inMemoryFlag=True)
        )

        self.step("uniqVcf", VcfUniq(vcf=self.sortFinal.out))

        self.step("compressFinal", BGZip(file=self.uniqVcf.out))

        self.step("indexFinal", Tabix(inp=self.compressFinal.out))

        self.output("somaticOutVcf", source=self.indexFinal)


if __name__ == "__main__":

    wf = FreeBayesSomaticWorkflow()
    wdl = wf.translate("wdl", to_console=True, to_disk=False, write_inputs_file=False)
