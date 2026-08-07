from setuptools import setup

setup(
    name="mcritweb",
    version="1.4.6",
    packages=["mcritweb"],
    include_package_data=True,
    install_requires=[
        "flask>=3.0",
        "werkzeug>=3.0",
        "flask-dropzone",
        "Pillow",
        "numpy",
        "scipy", 
        "fastcluster",
        "networkx",
        "mcrit>=1.5.3",
        "levenshtein",
        "markdown"
    ],
)
