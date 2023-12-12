from setuptools import setup

setup(
    name="mcritweb",
    version="1.2.17",
    packages=["mcritweb"],
    include_package_data=True,
    install_requires=[
        "flask==2.2.5",
        "werkzeug==2.3.3",
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
