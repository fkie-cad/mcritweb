from setuptools import setup

setup(
    name="mcritweb",
    version="0.12.1",
    packages=["mcritweb"],
    include_package_data=True,
    install_requires=[
        "flask",
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
