# MCRITweb

MCRITweb is a Flask-based user interface for [MCRIT](https://github.com/danielplohmann/mcrit), the MinHash-based Code Recognition & Investigation Toolkit.  
MCRITweb has been developed by Daniel Enders, Manuel Blatt, and Daniel Plohmann.

## Installation

We highly recommend using the dockerized deployment available at [docker-mcrit](https://github.com/danielplohmann/docker-mcrit).

If you instead want to go for a direct installation, a few dependencies have to be installed.  
First, ensure that Python 3.8+ is available, then simply use pip to cover the requirements:
```bash
# install python and MCRIT dependencies
$ sudo apt install python3 python3-pip
$ pip install -r requirements.txt 
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
 * 2023-08-29 v1.0.17 Clustering functions of link hunt.
 * 2023-08-25 v1.0.15 Integrated link hunt to result display.
 * 2023-06-06 v1.0.7 Extended result filters for family name, function offsets, and unique family function hits.
 * 2023-06-06 v1.0.6: Bugfix for use of new MatchingResult methods when showing 1v1 results.
 * 2023-06-02 v1.0.5: Fixed ResultView for Query results. Slight improvement to Jobs table. Adjusted API passthrough for function collections.
 * 2023-05-12 v1.0.4: Extended API passthrough for creation of matching jobs in MCRIT.
 * 2023-05-08 v1.0.3: More consistent result filter behavior.
 * 2023-04-14 v1.0.2: Started working on documentation. Fixed minor things.
 * 2023-04-10 v1.0.0: Milestone release for Botconf 2023.
 * 2023-04-10 v0.15.0: Shaping user role visitor more towards a demo account: limited visibility of menus/content, disallowed username/password change, but allowing them to upload files for query, up to size 1MB.
 * 2023-03-24 v0.14.2: API forward for adding / updating SmdaReports.
 * 2023-03-23 v0.14.1: UserInfo database object introduced and exposing apitoken in the UI.
 * 2023-03-21 v0.14.0: API forward for querying multiple function_entries by function_id.
 * 2023-03-19 v0.12.3: API forward for single SmdaFunction queries.
 * 2023-03-17 v0.12.1: Fix for special case of not rendering function graph, fix for default filters if no DB entry found.
 * 2023-03-15 v0.12.0: User now have apitokens that can be used to interact with the MCRIT instance behind mcritweb via api-passthrough (BREAKS DB -> ALTER TABLE user ADD apitoken VARCHAR).
 * 2023-03-14 v0.11.1: API calls are now shown on rendered graphs
 * 2023-03-14 v0.11.0: Users may now store a preference for default result filters (BREAKS DB -> CREATE TABLE user_filters).
 * 2023-03-13 v0.10.6: Filtering of family/sample result table is now possible.
 * 2023-02-27 v0.10.5: Now showing if function matches are unique in a family.
 * 2023-02-21 v0.10.4: More fixes and usability improvements on match result pages.
 * 2023-02-17 v0.10.2: Various usability improvements on match result pages.
 * 2023-01-15 v0.9.13: Allow filtering matching results by score, number of family matches, and exclude library matches.
 * 2022-12-15 v0.9.10: Allow setting Minhash fuzziness for candidate selection.
 * 2022-12-13 v0.9.7: Allow matching of arbitrary functions by their IDs.
 * 2022-11-18 v0.9.5: Modify and Delete functions for samples and families.
 * 2022-11-03 v0.9.1: Improved Unique Blocks Isolation and added YARA generation.
 * 2022-10-14 v0.9.0: Initial public beta release.


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
