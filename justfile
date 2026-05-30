clean: _clean _clean-pdf
    rm -rf ~/.data/resumator/Q47475003

_clean-pdf:
    rm -f *.pdf

_clean:
    rm -f *.aux
    rm -f *.bbl
    rm -f *.blg
    rm -f *.fdb_latexmk
    rm -f *.fls
    rm -f *.log
    rm -f *.out

lint:
    uvx ruff format .

build: _clean _clean-pdf
    sh build.sh
