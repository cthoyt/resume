clean: _clean
    rm ~/.data/resumator/Q47475003/*.json
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

build: _clean
    sh build.sh
