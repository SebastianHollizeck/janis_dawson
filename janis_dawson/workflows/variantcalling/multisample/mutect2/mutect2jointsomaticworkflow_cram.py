from datetime import date

from janis_core import Array, String
from janis_bioinformatics.data_types import CramCrai, FastaWithDict, VcfTabix
from janis_bioinformatics.tools import BioinformaticsWorkflow
from janis_bioinformatics.tools.bcftools import (
    BcfToolsConcat_1_9 as BcfToolsConcat,
    BcfToolsIndex_1_9 as BcfToolsIndex,
    BcfToolsNorm_1_9 as BcfToolsNorm,
)
from janis_bioinformatics.tools.dawson.createcallregions.base import CreateCallRegions

# these dont need cram, because they dont work on crams
from janis_bioinformatics.tools.gatk4 import (
    Gatk4CalculateContaminationLatest as CalculateContamination,
    Gatk4FilterMutectCallsLatest as FilterMutectCalls,
    Gatk4LearnReadOrientationModelLatest as LearnReadOrientationModel,
    Gatk4MergeMutectStatsLatest as MergeMutectStats,
)

# for these we need the special cram version because they work directly on the cram
from janis_bioinformatics.tools.gatk4.mutect2.versions import (
    GatkMutect2Cram_4_1_8 as Mutect2,
)

from janis_bioinformatics.tools.gatk4.getpileupsummaries.versions import (
    Gatk4GetPileUpSummariesCram_4_1_8 as GetPileUpSummaries,
)


class Mutect2JointSomaticWorkflowCram(BioinformaticsWorkflow):
    def id(self):
        return "Mutect2JointSomaticWorkflowCram"

    def friendly_name(self):
        return "Mutect2 joint somatic variant calling workflow"

    def tool_provider(self):
        return "Dawson Labs"

    def version(self):
        return "0.2"

    def bind_metadata(self):
        self.metadata.version = "0.2"
        self.metadata.dateCreated = date(2019, 10, 30)
        self.metadata.dateUpdated = date(2020, 12, 10)

        self.contributors = ["Sebastian Hollizeck"]
        self.metadata.keywords = [
            "variants",
            "mutect2",
            "variant caller",
            "multi sample",
        ]
        self.metadata.documentation = """
        This workflow uses the capability of mutect2 to call several samples at the same time and improve recall and accuracy through a joint model.
        Most of these tools are still in a beta state and not intended for main production (as of 4.1.4.0)
        There are also som major tweaks we have to do for runtime, as the amount of data might overwhelm the tools otherwise.
                """.strip()

    def constructor(self):

        # we have to split the bam into the ones of the normal sample (can be multiple) and the
        # tumor, because some tools only work with the tumor bams
        self.input("normalBams", Array(CramCrai))
        self.input("tumorBams", Array(CramCrai))

        # we also need the name of the normal sample (needs to be the name in the bams as well)
        self.input("normalName", String)

        self.input("biallelicSites", VcfTabix)

        self.input("reference", FastaWithDict)

        self.input("regionSize", int, default=10000000)

        self.input("panelOfNormals", VcfTabix)

        self.input("germlineResource", VcfTabix)

        self.step(
            "createCallRegions",
            CreateCallRegions(
                reference=self.reference, regionSize=self.regionSize, equalize=True
            ),
        )

        self.step(
            "mutect2",
            Mutect2(
                tumorBams=self.tumorBams,
                normalBams=self.normalBams,
                normalSample=self.normalName,
                intervals=self.createCallRegions.regions,
                reference=self.reference,
                panelOfNormals=self.panelOfNormals,
                germlineResource=self.germlineResource,
            ),
            scatter="intervals",
        )

        self.step("concat", BcfToolsConcat(vcf=self.mutect2.out))
        self.step("indexUnfiltered", BcfToolsIndex(vcf=self.concat.out))

        self.step(
            "learn", LearnReadOrientationModel(f1r2CountsFiles=self.mutect2.f1f2r_out)
        )

        self.step("mergeMutect2", MergeMutectStats(statsFiles=self.mutect2.stats))

        self.step(
            "pileup",
            GetPileUpSummaries(
                bam=self.tumorBams,
                sites=self.biallelicSites,
                intervals=self.biallelicSites,
                reference=self.reference,
            ),
        )

        self.step("contamination", CalculateContamination(pileupTable=self.pileup.out))

        self.step(
            "filtering",
            FilterMutectCalls(
                vcf=self.indexUnfiltered.out,
                reference=self.reference,
                segmentationFile=self.contamination.segOut,
                contaminationTable=self.contamination.contOut,
                readOrientationModel=self.learn.out,
                statsFile=self.mergeMutect2.out,
            ),
        )

        self.step(
            "normalise", BcfToolsNorm(vcf=self.filtering.out, reference=self.reference)
        )
        self.step("indexFiltered", BcfToolsIndex(vcf=self.normalise.out))
        self.output("out", source=self.indexFiltered.out)


if __name__ == "__main__":

    wf = Mutect2JointSomaticWorkflowCram()
    wdl = wf.translate("wdl", to_console=True, to_disk=False, write_inputs_file=False)
