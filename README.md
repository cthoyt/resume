# The Résumé of Charles Tapley Hoyt 

This repository contains my résumé and curriculum vitae (CV).
The latest PDF build for the [short form](https://github.com/cthoyt/resume/raw/master/main.pdf) and
[long form](https://github.com/cthoyt/resume/raw/master/cv.pdf) are available from GitHub.

For a more full history, see my [website](https://cthoyt.com), my [Wikidata](https://www.wikidata.org/wiki/Q47475003)
entry, and my [Scholia](https://tools.wmflabs.org/scholia/author/Q47475003) page.

## Build

To build my résumé as a PDF, clone the repository and use the following command:

```shell
git clone https://github.com/cthoyt/resume.git
cd resume
latexmk -pdf -interaction=nonstopmode -pvc main
latexmk -pdf -file-line-error -halt-on-error -interaction=nonstopmode main
```

CV

```shell
git clone https://github.com/cthoyt/resume.git
cd resume
python src/resumator/make_cv.py
latexmk -pdf -interaction=nonstopmode -pvc cv
latexmk -pdf -file-line-error -halt-on-error -interaction=nonstopmode cv
```
