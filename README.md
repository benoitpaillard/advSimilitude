# ADV Propulse – version corrigée

Cette version corrige les deux causes principales des puissances aberrantes :

1. Le diamètre orbital de la base est **0,300 m**, déduit automatiquement de `lambda = V/(omega D/2)`. Il n'est plus modifiable dans l'interface. La valeur 3,74 m ne doit pas être utilisée comme diamètre de référence de cet abaque.
2. La longueur de pale utilisée pour dimensionner les sorties CFD 2D est traitée comme une **longueur effective de post-traitement**. La valeur par défaut est 5,00 m, calibrée provisoirement sur les cas connus. Elle reste modifiable.

Le classeur contient également des pertes ponctuelles de séparateur décimal, donnant des facteurs x1000 dans certaines cellules. L'application répare automatiquement les colonnes redondantes avant interpolation. La colonne `DHP[W]`, cohérente et lisse, est utilisée comme ancre.

## Cas de contrôle

Avec une longueur effective de référence de 5,00 m :

- P200, longueur 0,300 m, 15 kn, lambda 1,3, Bmax 15° :
  - sans iso-Re : environ 14,34 kW
  - iso-Re sur V·D : environ 15,69 kW
  - essai : environ 16 kW

- P75.6, longueur 0,080 m, 14 kn, lambda 1,8, Bmax 15° :
  - sans iso-Re : environ 0,806 kW
  - iso-Re sur V·D : environ 1,126 kW
  - essai : environ 0,8 kW

Le point P75.6 est hors domaine en lambda et, en iso-Re, également hors domaine en vitesse équivalente. L'application affiche un avertissement rouge.

## Lancement

```bash
python3 -m pip install -r requirements.txt
streamlit run streamlit_app.py
```
