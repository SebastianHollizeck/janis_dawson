from setuptools import setup, find_packages

######## SHOULDN'T NEED EDITS BELOW THIS LINE ########

vsn = {}
with open("./janis_dawson/__meta__.py") as fp:
    exec(fp.read(), vsn)
version = vsn["__version__"]
description = vsn["description"]

with open("./README.md") as readme:
    long_description = readme.read()

setup(
    name="janis-pipelines.dawson",
    version=version,
    description=description,
    url="https://github.com/PMCC-BioinformaticsCore/janis-bioinformatics",
    author="Sebastian Hollizeck",
    author_email="sebastian.hollizeck@petermac.org",
    license="GNU",
    packages=["janis_dawson"]
    + ["janis_dawson." + p for p in sorted(find_packages("./janis_dawson"))],
    entry_points={
        "janis.extension": ["dawson=janis_dawson"],
        "janis.tools": [
            "dawson=janis_dawson.tools",
            "dawson_workflows=janis_dawson.workflows",
        ],
    },
    install_requires=["janis-pipelines.core >= 0.10.10"],
    zip_safe=False,
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
    ],
)
