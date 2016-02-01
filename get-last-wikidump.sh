LANG=$1
FILE=${LANG}wiki-latest-all-titles-in-ns0.gz

rm ${FILE}
wget https://dumps.wikimedia.org/${LANG}wiki/latest/${FILE}

gunzip -f ${FILE}
