from setuptools import setup

setup(
    name="mcritweb",
    version="1.2.0",
    packages=["mcritweb"],
    include_package_data=True,
    install_requires=[
        "flask==2.2.2",
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
