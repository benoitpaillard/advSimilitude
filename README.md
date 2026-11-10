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

## Variantes CFD — mise à jour du 10 novembre 2026

Le choix **Configuration CFD** ajoute trois variantes à la base de référence
(σ=1,425, DIR=−2,5°) : DIR=+2°, σ=1,7, et leur combinaison. La référence demeure
le choix par défaut ; les variantes sont disponibles avec la base compacte intégrée.
Une base importée utilise son propre interpolateur, sans ces corrections.

Les synthèses de la campagne comportent 1 705 cas uniques. Seuls les 1 300 cas
de variantes avec convergence périodique et bilan propulsif admissible alimentent
les corrections : DIR 679/831, σ=1,7 368/438, combinaison 253/435. Le pilote
de référence est compté séparément (1/1). Les 404 cas sans marqueur de convergence,
dont quatre anomalies manifestes, sont conservés pour la traçabilité mais exclus
du modèle. Le contrôle de convergence porte sur Mz entre deux tours ; il ne
constitue pas une validation du maillage ou de toutes les grandeurs mécaniques.

À V, lambda et Bmax identiques, sur 219 points communs convergés, les écarts
médians par rapport à la référence sont :

| Variante | Poussée | DHP | Rendement relatif | Mh max |
|---|---:|---:|---:|---:|
| DIR=+2° | −9,8 % | −10,5 % | +1,2 % | +11,0 % |
| σ=1,7 | +6,3 % | +6,5 % | −1,0 % | +32,7 % |
| Combinaison | −6,4 % | −6,7 % | −0,1 % | +48,2 % |

Ces résultats ne classent pas les variantes à poussée ou puissance imposée.
Le faible gain de rendement dépend du filtrage des cas ; augmenter la solidité
pénalise surtout le couple maximal de pale.

### Interpolation et qualité

L'application multiplie la base de référence par des rapports interpolés sur
(V, lambda, Bmax) pour la poussée, la DHP et Mh max. Pour la force latérale et
le couple de direction, qui peuvent traverser zéro, elle interpole une correction
additive normalisée par V². Le rendement et le couple propulsif moyen sont
recalculés à partir des efforts et de la puissance, pour conserver leur cohérence.
Les coefficients de poussée et de couple suivent les mêmes corrections.

Les points hors de l'enveloppe des cas convergés ne sont pas extrapolés. Un point
calculé puis rejeté reste explicitement indisponible, même si les voisins permettent
une interpolation. Ces points sont exclus des candidats faisables en optimisation.
Chaque résultat indique sa configuration, son origine (cas convergé ou correction
interpolée), le run quand il existe, et les limites de validité. Les rapports TXT
et les CSV d'optimisation conservent ces informations.

Le contrôle indépendant V=10 → 30 m/s, à lambda/Bmax fixes et convergence aux
deux vitesses, donne :

| Variante | Couples | Erreur poussée médiane / max | Erreur DHP médiane / max | Erreur Mh max médiane / max |
|---|---:|---:|---:|---:|
| σ=1,7 | 10 | 1,03 / 3,26 % | 0,73 / 2,62 % | 1,25 / 3,45 % |
| Combinaison | 9 | 2,45 / 5,83 % | 2,10 / 4,94 % | 1,78 / 6,84 % |

Il s'agit d'une validation de la stratégie par rapports, réalisée avant intégration
des points V=30 au modèle, et non d'une borne d'erreur applicable à toutes ses
prédictions. Aucun contrôle V=30 à lambda=0,5 ni à lambda=1,7/Bmax=25° n'a le
marqueur de convergence. La couverture entre 12 et 30 m/s reste clairsemée pour
les variantes à σ=1,7. Les quatre cas DIR à V=30 sont également exclus : la
correction de cette variante ne va pas au-delà de ses cas convergés à V=25.

Le pilote reproduit poussée et DHP à moins de 1 %, mais son Mh max diffère de
20 %. Les pics mécaniques demandent une validation séparée. Les courbes 360°
restent disponibles pour la référence ; elles sont désactivées pour les variantes,
dont seules les synthèses auditées sont intégrées. Les synthèses ne permettent pas
de reconstruire les efforts simultanés sur une pale.

### Sources, vérification et publication

`campaign_results.csv` conserve les synthèses et leurs indicateurs de convergence.
`campaign_metadata.json` enregistre les empreintes des instantanés sources et de
la base de référence, les paramètres géométriques, les anomalies et les erreurs
de validation. Le chargement vérifie les empreintes du CSV et de la base compacte.
Pour reconstruire les données depuis les instantanés d'ADVFoam :

```bash
python3 build_campaign_data.py ../campaigns/gaetan-20261022/analysis
```

Pour vérifier le modèle et les parcours Streamlit :

```bash
python3 -m pytest -q tests
```

Les tests couvrent les 1 300 points convergés, l'exclusion des anomalies et du
hors-domaine, les bilans physiques, les facteurs de similitude, l'optimisation,
l'évaluation d'un point et la conservation du fonctionnement de la référence.
`pytest` est une dépendance de développement, non requise par l'application.

L'application est publiée depuis la branche `main` du dépôt
`benoitpaillard/advSimilitude` sur Streamlit Community Cloud, avec
`streamlit_app.py` comme point d'entrée. Un push sur cette branche fournit
les nouveaux fichiers au service ; son état effectif doit être contrôlé après le push.
