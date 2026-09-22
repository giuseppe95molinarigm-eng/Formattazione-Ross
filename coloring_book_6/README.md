# ¡Ya tengo 6 años!

Production pipeline for the Spanish children's coloring / activity book
**“¡Ya tengo 6 años!”** — *Actividades, datos Curiosos y dibujos para colorear
para niños de 6 años* (AHLivros), formatted for **Amazon KDP paperback,
8.5 × 11 in, portrait**.

The book contains **101 coloring illustrations**. Every illustration sits on a
**left-hand page** and its Spanish text sits on the **facing right-hand page**.

This guide assumes **no programming experience**. Every Terminal command can be
copied and pasted as-is on **macOS**.

---

## Table of contents

1. [What this project does](#1-what-this-project-does)
2. [Install Python](#2-install-python)
3. [Open the project in Terminal](#3-open-the-project-in-terminal)
4. [Create the virtual environment](#4-create-the-virtual-environment)
5. [Install the dependencies](#5-install-the-dependencies)
6. [Configure Replicate](#6-configure-replicate)
7. [Where the manuscript goes](#7-where-the-manuscript-goes)
8. [Where the reference images go](#8-where-the-reference-images-go)
9. [Read the manuscript and analyse the references](#9-read-the-manuscript-and-analyse-the-references)
10. [Generate illustrations 001–020](#10-generate-illustrations-001020)
11. [Validate the batch](#11-validate-the-batch)
12. [Create the review sheet](#12-create-the-review-sheet)
13. [Regenerate a single illustration](#13-regenerate-a-single-illustration)
14. [Approve a batch and move to the next](#14-approve-a-batch-and-move-to-the-next)
15. [Build the final book](#15-build-the-final-book)
16. [Run the KDP preflight](#16-run-the-kdp-preflight)
17. [Where the final files are](#17-where-the-final-files-are)
18. [Command reference](#18-command-reference)
19. [Cost control](#19-cost-control)
20. [If something goes wrong](#20-if-something-goes-wrong)

---

## 1. What this project does

It runs the whole book production in stages that you control:

| Stage | What happens |
|---|---|
| **Parse** | Reads the Word manuscript and stores all 101 Spanish texts as data. The Spanish is copied **word for word** and never rewritten. |
| **Analyse** | Measures the previous book's illustrations to lock in the collection's visual style. |
| **Prompts** | Builds a detailed English instruction for each illustration. |
| **Generate** | Calls Replicate to draw the illustrations — **in batches of 20, and only when you approve**. |
| **Validate** | Checks every image automatically (size, resolution, whiteness, stray text, duplicates…). |
| **Review** | Produces a contact sheet so you can look at a whole batch at once. |
| **Build** | Lays out the print-ready interior PDF. |
| **Preflight** | Checks the finished PDF against Amazon KDP's requirements. |

Nothing is ever generated automatically. **You approve every batch.**

---

## 2. Install Python

macOS ships with an old Python. Install a current one.

Check what you have:

```bash
python3 --version
```

If it prints **3.10 or higher**, skip ahead to step 3.

Otherwise, install [Homebrew](https://brew.sh) (paste this in Terminal):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then install Python:

```bash
brew install python@3.12
```

---

## 3. Open the project in Terminal

Open **Terminal** (press `⌘ Space`, type `Terminal`, press Return), then move
into the project folder. If the folder is on your Desktop:

```bash
cd ~/Desktop/coloring_book_6
```

Confirm you are in the right place — you should see `main.py` listed:

```bash
ls
```

> **Tip:** instead of typing the path, type `cd ` (with a space) and then drag
> the project folder from Finder onto the Terminal window and press Return.

---

## 4. Create the virtual environment

A virtual environment keeps this project's software separate from the rest of
your Mac. Create it **once**:

```bash
python3 -m venv .venv
```

Now activate it. **You must do this every time you open a new Terminal window:**

```bash
source .venv/bin/activate
```

Your prompt will start showing `(.venv)`. That is how you know it is active.

---

## 5. Install the dependencies

With the environment active:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This takes a couple of minutes. It only needs doing once.

---

## 6. Configure Replicate

The illustrations are drawn by an AI model hosted on
[Replicate](https://replicate.com). You need an account and an API token.

1. Sign in at <https://replicate.com>.
2. Go to <https://replicate.com/account/api-tokens> and copy your token
   (it starts with `r8_`).
3. Create your private settings file by copying the example:

```bash
cp .env.example .env
```

4. Open `.env` in TextEdit:

```bash
open -a TextEdit .env
```

5. Replace `your_replicate_api_token_here` with your token, so the file reads:

```
REPLICATE_API_TOKEN=r8_your_real_token
```

6. Save and close.

Now check that everything is wired up correctly. This command **does not
generate an image and costs nothing** — it just verifies your token and prints
the model's current list of accepted settings:

```bash
python main.py doctor
```

You should see your model, a confirmation that your token was found, and the
line `OK: every field the pipeline sends exists in the live schema.`

> **Security:** `.env` holds your private token. It is already listed in
> `.gitignore`, so it is never committed to Git, never printed in logs, and
> never written into the PDF or any metadata file. Do not email it or paste it
> into a chat.

---

## 7. Where the manuscript goes

The Spanish manuscript lives here:

```
manuscript/manuscript.docx
```

It is already in place. If you ever replace it, keep the same filename, or
update `paths.manuscript` in `config.yaml`.

The manuscript is the **single source of truth**. The pipeline never rewrites,
translates, shortens or corrects your Spanish.

---

## 8. Where the reference images go

Illustrations from the earlier books in the collection live here:

```
references/reference_images/
```

They are already extracted from the previous book (*¡Ya tengo 5 años!*). They do
two jobs:

* they are measured to define the collection's visual style, and
* three of them are sent to the AI model as **style references** so the new book
  matches the series.

Which three are used is set in `config.yaml` under
`image_generation.reference_images`. They guide the **style only** — every new
illustration is an original composition.

---

## 9. Read the manuscript and analyse the references

Run these three commands in order:

```bash
python main.py parse
python main.py analyze-refs
python main.py prompts
```

* `parse` — reads the Word file and confirms there are exactly 101 entries in 5 parts.
* `analyze-refs` — measures the previous book's line weight, ink coverage and margins.
* `prompts` — assembles the full drawing instruction for each illustration.

At any point you can see where the project stands:

```bash
python main.py status
```

---

## 10. Generate illustrations 001–020

**First, look at what it will do and what it will cost — this is free:**

```bash
python main.py plan --start 1 --end 20
```

This prints the model, the images to be drawn, the number of paid API calls and
the estimated cost. Nothing is generated.

When you are happy, generate the batch:

```bash
python main.py generate --start 1 --end 20
```

You will be asked to confirm before any money is spent:

```
Proceed and spend up to $14.40 on Replicate? [y/N]
```

Type `y` and press Return. Type anything else to cancel.

Each illustration is drawn, converted to the exact print size, and checked. If
an image fails its checks it is automatically redrawn (up to 3 attempts) and the
rejected version is kept in `images/rejected/` so you can compare.

> **This is safe to interrupt.** If your Mac sleeps, the network drops or you
> close Terminal, just run the same command again. Images that already finished
> and passed are skipped, not paid for twice.

---

## 11. Validate the batch

```bash
python main.py validate --start 1 --end 20
```

You get a table showing, for each image: pixel size, effective print
resolution, how much of the page is white, how much is ink, and any problems.

It checks all of the following automatically:

* exact pixel dimensions (2550 × 3300) and portrait orientation
* correct 8.5 : 11 aspect ratio
* at least 300 PPI of **real pixels** at final print size
* a mostly white background and enough black line work
* no unexpected colour and no grey shading
* nothing printed inside the safe margin, and no artwork clipped at an edge
* correct filename for the right number
* **suspected text or lettering inside the artwork**
* duplicate and near-duplicate images (perceptual hashing)

---

## 12. Create the review sheet

```bash
python main.py contact-sheet --start 1 --end 20
```

This writes a contact sheet and a review PDF to the `review/` folder. Open them:

```bash
open review/
```

The illustration number is printed **above** each thumbnail, in the sheet's own
caption strip. It is **never** part of the coloring artwork itself.

Look through the batch and check:

* does each picture actually show the idea from its Spanish text?
* is it the same 6-year-old boy throughout?
* where other children appear, do they look like different individuals?
* any letters, numbers or writing anywhere? (there must be none)
* hands and fingers correct?
* do the poses and settings vary, rather than repeating?

---

## 13. Regenerate a single illustration

If, say, number 7 is not right:

```bash
python main.py regenerate --id 7
```

You can list several at once:

```bash
python main.py regenerate --id 7 --id 12 --id 19
```

If an illustration keeps coming back wrong, improve its scene description in
`prompts/scenes.json`, then rebuild its prompt and regenerate:

```bash
python main.py prompts --id 7
python main.py regenerate --id 7
```

`regenerate` is the only command that replaces artwork that already passed.
Ordinary `generate` never overwrites approved work.

---

## 14. Approve a batch and move to the next

There is no "approve" button — **approval is you choosing to start the next
batch.** Approved images simply stay where they are, and `generate` skips them
from then on.

The five batches follow the five parts of the manuscript:

| Batch | Illustrations | Command |
|---|---|---|
| 1 | 001–020 | `python main.py generate --start 1 --end 20` |
| 2 | 021–040 | `python main.py generate --start 21 --end 40` |
| 3 | 041–060 | `python main.py generate --start 41 --end 60` |
| 4 | 061–080 | `python main.py generate --start 61 --end 80` |
| 5 | 081–101 | `python main.py generate --start 81 --end 101` |

For each batch, repeat the same four steps:

```bash
python main.py plan          --start 21 --end 40   # free: check the cost
python main.py generate      --start 21 --end 40   # paid
python main.py validate      --start 21 --end 40
python main.py contact-sheet --start 21 --end 40
```

> Scene descriptions are written one batch at a time, so that each batch can be
> designed with the previous batch's results in hand. If you run `generate` for
> a batch whose scenes have not been written yet, it stops safely and tells you,
> without spending anything.

---

## 15. Build the final book

Once all 101 illustrations are approved:

```bash
python main.py build-book
```

This lays out the complete interior and writes `output/final_interior.pdf`.

The layout is verified **before** anything is drawn. If the image-left /
text-right relationship could not be honoured, the build refuses to run rather
than produce a wrong book. The build prints a confirmation like:

```
pages              : 218 (even: yes)
illustrations      : 101 (all on verso/left)
text pages         : 101 (all on recto/right)
gutter (KDP table) : 0.625in for 218 pages
facing-page contract: VERIFIED (image verso / text recto, all 101)
```

Margins are calculated from the **actual** final page count using Amazon's
current inside-margin table, not guessed.

---

## 16. Run the KDP preflight

```bash
python main.py preflight
```

This writes `output/preflight_report.txt` and prints it. Every check is marked
`PASS`, `WARNING` or `FAIL`, and the report ends with either:

```
RESULT: READY FOR KDP UPLOAD — all critical checks passed.
```

or a list of the critical problems to fix. **Do not upload the book until the
preflight reports READY.**

`WARNING` lines are not blockers — they are things worth a human glance, such as
an image the text-screen flagged for a closer look.

---

## 17. Where the final files are

| File | What it is |
|---|---|
| `output/final_interior.pdf` | **The print-ready interior to upload to KDP.** |
| `output/preflight_report.txt` | The full technical check report. |
| `images/final/001.png` … `101.png` | The 101 production illustrations, 2550 × 3300 px. |
| `review/contact_sheet_*.png` | Batch review sheets. |
| `review/review_*.pdf` | Batch review PDFs. |
| `images/rejected/` | Attempts that failed QC, kept for comparison. |
| `images/raw/` | Untouched model output, before processing. |
| `data/entries.json` | The 101 Spanish texts, verbatim. |
| `data/character_spec.json` | The recurring character and style specification. |
| `data/generation_metadata.json` | What was generated, how, and its QC result. |
| `data/page_map.json` | Every page of the book and what is on it. |
| `prompts/generated_prompts.json` | The exact prompt used for each illustration. |

To open the finished PDF:

```bash
open output/final_interior.pdf
```

---

## 18. Command reference

```bash
python main.py parse                          # manuscript -> structured data
python main.py analyze-refs                   # measure the collection style
python main.py prompts                        # build all prompts
python main.py prompts --id 7                 # rebuild one prompt
python main.py doctor                         # check Replicate setup (free)
python main.py status                         # progress overview
python main.py plan --start 1 --end 20        # preview a batch + cost (free)
python main.py generate --start 1 --end 20    # PAID: generate a batch
python main.py generate --start 1 --end 20 --dry-run   # plan only, no charge
python main.py validate --start 1 --end 20    # QC a range
python main.py contact-sheet --start 1 --end 20
python main.py regenerate --id 7              # PAID: redraw one image
python main.py build-book                     # lay out the interior PDF
python main.py preflight                      # KDP compliance report
```

Useful flags:

| Flag | Meaning |
|---|---|
| `--dry-run` | Show the plan and stop before spending anything. |
| `--yes` | Skip the cost confirmation question (for unattended runs). |
| `--force` | Allow `generate` to replace images that already passed. **Use with care.** |
| `--id N` | Act on one illustration; repeatable. |
| `--config PATH` | Use a different settings file. |

---

## 19. Cost control

Image generation costs real money, so the pipeline is deliberately cautious:

* **Nothing runs automatically.** All 101 images are never generated in one go.
* Every paid command **prints the cost first and asks for confirmation.**
* Finished, passing images are **skipped** — you never pay twice for the same picture.
* Replacing approved artwork requires `regenerate` or an explicit `--force`.
* Retries are capped (3 attempts per image by default, set in `config.yaml`).
* Failed attempts are kept rather than silently redone.

Current settings: `google/nano-banana-pro` at 4K, about **$0.24 per image**.

| | Images | Expected cost |
|---|---|---|
| One batch | 20 | ≈ $5.50 |
| Whole book | 101 | ≈ $28 |

Cheaper option: set `output_resolution: "2k"` in `config.yaml` (roughly
$0.13–0.15 per image). The model then returns a smaller picture that must be
enlarged to reach print size, which softens the line work — the preflight will
warn you when this happens. **4K is recommended for print.**

To change the model entirely, edit `image_generation.model` and
`active_profile` in `config.yaml`. Profiles for FLUX.2 Pro and Ideogram v3 are
already included. After switching, always run `python main.py doctor` to confirm
the settings match that model's live API before generating.

---

## 20. If something goes wrong

**`command not found: python`**
The virtual environment is not active. Run `source .venv/bin/activate`.

**`REPLICATE_API_TOKEN is not set`**
Create `.env` as described in [step 6](#6-configure-replicate) and paste your token in.

**`doctor` reports it cannot reach the Replicate API**
Check your internet connection, and that your token is valid and your Replicate
account has billing set up. A `403` means the token was rejected or has no
credit.

**Generation stopped halfway through**
Just run the same `generate` command again. Completed images are skipped and not
paid for again.

**`no scene authored yet for id(s): 021…`**
That batch's scene descriptions have not been written yet. They are written one
batch at a time, on purpose. Nothing was charged.

**An image keeps failing validation**
Read the reason in the `validate` output. If it is about resolution, raise
`output_resolution` to `4k`. If it is about stray text or a wrong scene, improve
that entry in `prompts/scenes.json`, then run `python main.py prompts --id N`
followed by `python main.py regenerate --id N`.

**`build-book` says illustrations are missing**
Run `python main.py status` to see which batches are incomplete.

**Preflight reports a critical failure**
Fix what it names and re-run `build-book` then `preflight`. The report tells you
exactly which check failed and why.

---

### Project layout

```
coloring_book_6/
├── README.md               this guide
├── requirements.txt        Python dependencies
├── config.yaml             all settings (model, sizes, margins, QC limits)
├── main.py                 the command-line tool
├── .env                    your private Replicate token (never committed)
├── .env.example            template for .env
├── manuscript/             the Spanish .docx manuscript
├── references/             previous books' artwork + the reference images
├── fonts/                  Poppins (SIL Open Font License)
├── data/                   parsed manuscript, character spec, metadata, page map
├── prompts/                master style prompt, scene designs, final prompts
├── scripts/                the pipeline modules
├── images/raw|final|rejected/
├── review/                 contact sheets and review PDFs
└── output/                 final_interior.pdf + preflight_report.txt
```

---

*Fonts: Poppins, © The Poppins Project Authors, SIL Open Font License 1.1
(`fonts/Poppins-OFL.txt`) — free for commercial print use.*
