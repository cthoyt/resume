# The Résumé of Charles Tapley Hoyt 

This repository contains my résumé (or curriculum vitae, as it's called in
Europe). Click [here](https://github.com/cthoyt/resume/raw/master/main.pdf)
to get the PDF of the latest build from GitHub.

For a more full history, see my [website](https://cthoyt.com), my [Wikidata](https://www.wikidata.org/wiki/Q47475003)
entry, and my [Scholia](https://tools.wmflabs.org/scholia/author/Q47475003) page.

## Build

To build my résumé as a PDF, clone the repository and use the following command:

```shell
$ git clone https://github.com/cthoyt/resume.git
$ cd resume
$ latexmk -pdf -pvc main
```

To build my CV as a PDF, run the following:

```shell
$ python fill_cv.py
$ latexmk -pdf -pvc cv
```
