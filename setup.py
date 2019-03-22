import setuptools

setuptools.setup(
    name="bhlaspaceapiclient",
    version="0.0.1",
    author="Bentley Historical Library",
    description="BHL ArchivesSpace API Wrapper",
    packages=setuptools.find_packages(),
    install_requires=[
        "requests",
        "lxml"
    ]
)
