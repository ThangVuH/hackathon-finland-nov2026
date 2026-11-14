# Stoa — version 1.1

Un plan, une question, une réponse dont on sait si elle est fiable.

Le front, `STOA-eyes`, ouvre un plan et pose une question. Deux moteurs répondent séparément. Le détecteur entraîné compte les fenêtres et les portes. Le modèle de vision propose une réponse et des rectangles. Le système ne marque le compte **fiable** que lorsque les deux totaux sont égaux et que les rectangles se recouvrent. Sinon le compte est **à vérifier** : les rectangles en désaccord restent surlignés, et un clic les garde ou les retire. Un fichier hors du domaine (IFC, PDF, planche d’archive) est refusé, sans compte inventé.

```
STOA-eyes/     l'application (chat, plan, boîtes)
counting/      le détecteur, la règle d'arbitrage, la mesure
eda/eda.ipynb  l'exploration du preview Junction
```

## Lancer l'application

Deux processus. Le service de comptage d'abord, puis le site.

### 1. Le détecteur

Python 3.13, avec PyTorch, Ultralytics, FastAPI, Pillow et `python-multipart`.

```powershell
cd counting
py -3.13 -m pip install torch ultralytics fastapi uvicorn python-multipart pillow
py -3.13 -m uvicorn server:app --port 8765
```

Le service écoute `http://127.0.0.1:8765`. Il n'a pas de page à la racine : `GET /` répond 404. Les routes sont `/health`, `/detect` et `/arbitrate`.

`/detect` reçoit l'image et la question. Il renvoie le total, les rectangles sur l'échelle 0–1000 (`ymin, xmin, ymax, xmax`) et un indice de confiance. Le poids utilisé est `counting/runs/window-door/weights/best.pt`. Le seuil, choisi sur les plans de validation, est dans `counting/detector_threshold.txt` (0,40).

### 2. Le site

Node.js 22 ou plus récent.

```powershell
cd STOA-eyes
npm install
npm run dev
```

Le serveur de dev affiche une URL, en général `http://localhost:8080/`.

La clé du modèle de vision se met dans `STOA-eyes/.env`, qui ne doit pas être commité :

```
LOVABLE_API_KEY=your-key
```

Sans cette clé, un comptage de fenêtres ou de portes vient du détecteur seul et reste marqué « à vérifier ». Une autre question (pièces, poteaux, surface) répond que le service d'IA n'est pas configuré. Si le détecteur n'est pas sur le port 8765, définir `DETECTOR_URL`.

Sur un terminal ouvert avant l'installation de Node, `npm` est inconnu. Il faut en ouvrir un nouveau.

## Ce que fait l'arbitrage

| Situation | Badge | Ce qui est affiché |
|---|---|---|
| Fenêtres ou portes, totaux égaux, boîtes superposées | RELIABLE | le total du détecteur |
| Fenêtres ou portes, totaux ou boîtes en désaccord | CHECK | les rectangles litigieux, cliquables |
| Autre question | NOT CHECKED | la réponse du modèle de vision, avec un avertissement |
| IFC, PDF, nom d'archive (`_sheet_`, HABS, Finna, Europeana, Wikimedia) | OUT OF SCOPE | aucun compte |

La règle est dans `counting/arbitrate.py`. Le front ne fait que l'afficher : `STOA-eyes/src/lib/vision.server.ts` appelle le service, puis `detections.ts` remet les rectangles au canevas.

```powershell
cd counting
py -3.13 -m unittest test_checker.py
```

## La mesure

Le découpage tenu à l'écart est dans `counting/eval_split.csv` : 36 plans, 64 questions de fenêtres et de portes. Ce n'est pas un bloc de 27 plans. Le seuil est choisi sur 36 autres plans de validation.

Relancer le rapport, sans refaire les prédictions déjà en cache :

```powershell
cd counting
py -3.13 compare_configs.py
```

Résultat actuel du détecteur seul, seuil 0,40 :

- plans exacts : 4/36 (11,1 %)
- questions exactes : 17/64 (26,6 %), dont 19 à une unité et 28 à deux unités ou plus

La colonne du modèle de vision et la courbe « précision quand le système se dit sûr » se remplissent seulement si `LOVABLE_API_KEY` est définie. Les réponses sont alors écrites dans `counting/cache/vision.jsonl`. Le détail déjà calculé est dans `counting/comparison_report.txt`.

## L'EDA

`eda/eda.ipynb` décrit le preview Junction : volumes, types de questions (compte, aire, longueur, volume, texte), langues, et des exemples de plans. Il lui faut le dossier `junction-dataset-preview` (ou le zip du même nom) à la racine de ce dépôt, ou dans le dossier d'où le notebook est lancé.

```powershell
pip install jupyter pandas matplotlib pillow pymupdf
jupyter notebook eda/eda.ipynb
```

PyMuPDF sert à afficher les PDF. Sans lui, le notebook le signale et continue sur les images.

Le preview et son zip ne sont pas dans git : le zip pèse environ 480 Mo, et GitHub refuse un fichier au-delà de 100 Mo.

## Réentraîner le détecteur

Les tuiles d'images ne sont pas versionnées. Elles se reconstruisent à partir des SVG et du preview :

```powershell
cd counting
py -3.13 export_yolo.py
py -3.13 train_detector.py
```

`counting/yolo/dataset.yaml` pointe vers le dossier `yolo`. L'entraînement écrit un nouveau `runs/window-door/weights/best.pt`.

## Ce qui reste hors du dépôt

| Fichier | Pourquoi |
|---|---|
| `junction-dataset-preview/` et son zip | le preview complet, au-delà de la limite GitHub |
| `counting/weights/model_best_val_loss_var.pkl` | checkpoint CubiCasa publié, 199 Mo, utilisé seulement par `run_published.py` |
| `counting/yolo/images` et `labels` | tuiles régénérées par `export_yolo.py` |
| `node_modules/`, `__pycache__/` | dépendances installées |
| `.env` | la clé du modèle de vision |
