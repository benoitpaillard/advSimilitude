# ADV Propulse – version corrigée

Cette version corrige les deux causes principales des puissances aberrantes :

1. Le diamètre orbital de la base est **0,300 m**, déduit automatiquement de `lambda = V/(omega D/2)`. Il n'est plus modifiable dans l'interface. La valeur 3,74 m ne doit pas être utilisée comme diamètre de référence de cet abaque.
2. La longueur de pale utilisée pour dimensionner les sorties CFD 2D est une **longueur de post-traitement propre à chaque base**. Elle est pré-remplie d'après le nom du classeur et reste modifiable.

L'ancienne base contient également des pertes ponctuelles de séparateur décimal, donnant des facteurs x1000 dans certaines cellules. L'application répare automatiquement les colonnes redondantes avant interpolation (la colonne `DHP[W]`, cohérente et lisse, sert d'ancre). Un classeur sain, comme la base bundlée actuelle, n'est pas modifié.

## Base bundlée

La base par défaut est `adv_propulse_database_Lpale0.375m.npz` (10,7 Mo) : version compacte du classeur `outputAll_Lpale0.375m.xlsx` (51,7 Mo ; feuille `Summary` + 905 feuilles `run.*` sur 360°, envergure de pale de post-traitement 0,375 m). La conversion est sans perte : les valeurs rechargées sont identiques à celles du classeur, et le chargement est plus rapide (environ 2 s).

Pour convertir un nouveau classeur `outputAll` :

```bash
python3 build_compact_database.py outputAll_Lpale0.375m.xlsx adv_propulse_database_Lpale0.375m.npz
```

Le fichier `.npz` est une archive numpy standard (`numpy.load`) : synthèse, courbes en float32 (6 chiffres significatifs, comme le classeur) et métadonnées, compressées en LZMA. L'interface accepte aussi bien un `.xlsx` qu'un `.npz` en remplacement de la base bundlée. L'ancienne base `adv_propulse_database.xlsx` (synthèse seule, longueur effective calibrée à 5,00 m) reste dans le dépôt.

## Cas de contrôle

| Cas | Base actuelle (0,375 m) | Ancienne base (5,00 m calibrés) | Essai |
|---|---|---|---|
| P200, pale 0,300 m, 15 kn, lambda 1,3, Bmax 15°, sans iso-Re | 12,78 kW | 14,34 kW | ~16 kW |
| idem, iso-Re sur V·D | 13,98 kW | 15,69 kW | |
| P75.6, pale 0,080 m, 14 kn, lambda 1,8, Bmax 15°, sans iso-Re | 0,718 kW | 0,806 kW | ~0,8 kW |
| idem, iso-Re sur V·D | 1,003 kW | 1,126 kW | |

L'écart de 11 % entre les deux bases vient de l'envergure : la base actuelle équivaut à l'ancienne avec 5,61 m (envergure d'origine du post-traitement) au lieu des 5,00 m calibrés.

Le point P75.6 est hors domaine en lambda et, en iso-Re, également hors domaine en vitesse équivalente. L'application affiche un avertissement rouge.

## Longueur de pale effective de la base

Les calculs CFD sont quasi-2D : le classeur contient des efforts obtenus en multipliant les résultats par une envergure de pale. En mode `2d`, l'outil multiplie les sorties par `H_cible / H_base` ; `H_base` doit donc être l'envergure utilisée pour construire le classeur utilisé. Elle est lue dans le nom du fichier (`…_Lpale0.375m` → 0,375 m) ; à défaut, l'interface demande de la vérifier.

## Simulation interpolée sur 360°

Si la base utilisée contient les courbes sur 360° (base compacte bundlée, ou classeur `outputAll` complet avec ses feuilles `run.*`), l'application génère pour le point évalué (ou le meilleur point en optimisation) un fichier au format d'une simulation standard :

- toutes les colonnes des feuilles `run.*` sont interpolées à θ fixé sur (V, lambda, Bmax), avec le même schéma que les grandeurs moyennes, puis mises à l'échelle avec les mêmes facteurs (efforts, moments, puissance ; `beta`, `R45`, `ω50`, `R54` sont cinématiques et inchangés ; `alpha` est recalculé depuis Fx, Fy) ;
- la moyenne des courbes redonne la poussée, la DHP, etc. affichées par l'outil ; `Mh max` est le maximum de |Mh| sur la courbe interpolée ;
- la feuille `Efforts pale` donne, pour une pale, Mh, Fx, Fy et Fh = √(Fx² + Fy²) simultanés sur le tour, et les cas critiques : Mh max, Mh min, Fh max et la pire combinaison selon l'indice `|Mh|/Mh_ref + Fh/Fh_ref` (références = valeurs admissibles si renseignées, sinon maxima sur le tour).

Ce fichier n'est pas un calcul CFD : entre deux runs de la base, les pics peuvent être légèrement lissés. Hors domaine, les courbes sont celles du run le plus proche.

## Lancement

```bash
python3 -m pip install -r requirements.txt
streamlit run streamlit_app.py
```
