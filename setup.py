from setuptools import setup

setup(
    name="mcritweb",
    version="1.1.7",
    packages=["mcritweb"],
    include_package_data=True,
    install_requires=[
        "flask>=2.3.1",
        "flask-dropzone",
        "Pillow",
        "numpy",
        "scipy", 
        "fastcluster"
        "networkx",
        "mcrit",
        "levenshtein"
    ],
)
