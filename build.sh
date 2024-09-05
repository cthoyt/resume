rm *.aux
rm *.bbl
rm *.blg
rm *.fdb_latexmk
rm *.fls
rm *.log
rm *.out

rm *.pdf
python src/resumator/make_cv.py
pdflatex -interaction=nonstopmode cv.tex
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode funding.tex
pdflatex -interaction=nonstopmode publications.tex

rm *.aux
rm *.bbl
rm *.blg
rm *.fdb_latexmk
rm *.fls
rm *.log
rm *.out
