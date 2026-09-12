# MCRITweb

MCRITweb is a Flask-based user interface for the [MinHash-based Code Recognition & Investigation Toolkit (MCRIT)](https://github.com/danielplohmann/mcrit).  
MCRITweb has been developed by Daniel Enders, Manuel Blatt, and Daniel Plohmann.

## Installation

We highly recommend using the dockerized deployment available at [docker-mcrit](https://github.com/danielplohmann/docker-mcrit).

If you instead want to go for a direct installation, a few dependencies have to be installed.  
First, ensure that Python 3.12+ is available, then install MCRITweb with its dependencies:
```bash
# install python, then MCRITweb and its dependencies
$ sudo apt install python3 python3-pip
$ pip install -e .
```

Obviously, also make sure that the backend [MCRIT](https://github.com/danielplohmann/mcrit) is fully installed, configured, and running.


## Usage

### Dockerized Usage

We highly recommend to use the fully packaged [docker-mcrit](https://github.com/danielplohmann/docker-mcrit) for trivial deployment and usage.  
First and foremost, this will ensure that you have fully compatible versions across all components.

### Standalone Usage

If you instead want to run MCRITweb as a standalone tool, the following steps will enable this:

Running flask commands requires you to set environment variables in your shell:  
`$ source ./flask_env.sh`

before the first usage, create an empty database:   
`$ flask init-db`

and then to run MCRITweb, execute:  
`$ flask run`

Note that most functionality of MCRITweb will only work if an MCRIT backend is configured and available.


## Version History

See [CHANGELOG.md](CHANGELOG.md) for the full release history.


## Credits & Notes

MCRITweb uses the following projects:  
* the awesome [CFGExplorer](https://github.com/hdc-arizona/cfgexplorer) library, published by the Humans, Data, and Computers Lab at CS Arizona, is used to visualize disassembly.  
* `bootstrap`, `jquery`, and `font-awesome` for its appearence. 

Pull requests welcome! :)


## License
```
    MCRITweb
    Copyright (C) 2022  Daniel Enders, Manuel Blatt, Daniel Plohmann

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
    
    Some plug-ins and libraries may have different licenses. 
    If so, a license file is provided in the plug-in's folder.
```
