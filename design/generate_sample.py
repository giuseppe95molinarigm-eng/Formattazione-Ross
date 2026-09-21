import json, re, html

recs = json.load(open("/home/user/Formattazione-Ross/master/master-recipes.json"))
def get(title, ch=1):
    return next(r for r in recs if r["title"] == title and r["chapter_num"] == ch)

QTY_RE = re.compile(
    r"^([\d¼½¾⅓⅔⅛⅜⅝⅞./\-\s]+(?:tablespoons?|teaspoons?|tbsp|tsp|cups?|ounces?|oz\.?|pounds?|lbs?\.?|cloves?|packets?|cans?|jars?|bay leaf|bay leaves)?)\s+(.*)$",
    re.IGNORECASE,
)

def esc(s):
    return html.escape(s, quote=False).replace("'", "&#8217;")

def qty_li(line, cls="ingredient-list"):
    m = QTY_RE.match(line.strip())
    if m and m.group(1).strip() and any(ch.isdigit() or ch in "¼½¾⅓⅔⅛⅜⅝⅞" for ch in m.group(1)):
        qty, rest = m.group(1).strip(), m.group(2).strip()
        return f'<li><span><span class="qty">{esc(qty)}</span> {esc(rest)}</span></li>'
    return f"<li>{esc(line.strip())}</li>"

def ingredient_block(items):
    return "\n".join(qty_li(i) for i in items)

def instructions_block(items):
    return "\n".join(f"<li>{esc(i)}</li>" for i in items)

def meta_row(r):
    f = r["fields"]
    parts = []
    if f.get("servings"):
        parts.append(f'<div class="meta-item"><span class="meta-label">Servings</span><span class="meta-value">{esc(f["servings"])}</span></div>')
    if f.get("serving_size"):
        parts.append(f'<div class="meta-item"><span class="meta-label">Serving Size</span><span class="meta-value">{esc(f["serving_size"])}</span></div>')
    if f.get("yield"):
        parts.append(f'<div class="meta-item"><span class="meta-label">Yield</span><span class="meta-value">{esc(f["yield"])}</span></div>')
    return '<div class="meta-row">' + "\n".join(parts) + "</div>"

def nutrition_html(r):
    n = r["fields"].get("nutrition")
    if not n:
        return ""
    return f'''<div class="nutrition-panel">
      <span class="n-label">Nutrition (per serving)</span>
      <div class="n-values">{esc(n)}</div>
    </div>'''

def storage_html(r):
    s = r["fields"].get("storage")
    if not s:
        return ""
    return f'''<div class="storage-callout">
      <span class="s-label">Storage</span>
      <div class="s-text">{esc(s)}</div>
    </div>'''

def jar_ingredients(r):
    return r["fields"].get("whats_in_jar") or r["fields"].get("ingredients") or []

def add_ingredients(r):
    return r["fields"].get("what_to_add") or []

def jar_label(r):
    return "What&#8217;s in the Jar?" if r["fields"].get("whats_in_jar") else "Ingredients"

PAGE_SHELL = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../tokens.css">
<style>{extra_style}</style>
</head>
<body>
<div class="page guides {side}">
  <div class="trim-line"></div>
  <div class="safe-line"></div>
  <span class="label-tag">{tag}</span>
  {running_head}
  {folio}
  <div class="content">
    {body}
  </div>
</div>
</body>
</html>"""

def running_head(side, left_text, right_text, show=True):
    if not show:
        return ""
    text = left_text if side == "page-left" else right_text
    align = "left: calc(var(--bleed) + var(--margin-outer));" if side == "page-left" else "right: calc(var(--bleed) + var(--margin-outer));"
    return f'<div class="running-head">{esc(text)}</div>'

def folio(side, num, show=True):
    if not show:
        return ""
    return f'<div class="folio">{num}</div>'

# ---------------------------------------------------------------------------
# 1. CHAPTER OPENER
# ---------------------------------------------------------------------------
chapter_opener_body = """
    <div style="position:absolute; top:0; bottom:0; left:0; width:38%; display:flex; flex-direction:column; justify-content:center;">
      <div class="kicker" style="margin-bottom:10px;">Chapter One</div>
      <div class="chapter-number">01</div>
      <div class="chapter-title" style="margin-top:6px;">Meal-Ready<br>Dry Mixes &amp;<br>Pantry Helpers</div>
      <div style="margin-top:22px; width:46px; border-top:2pt solid var(--terracotta);"></div>
      <div class="recipe-intro" style="margin-top:18px; max-width:300px; font-size:11.5pt;">
        Thirty-one jars built to carry the whole weeknight &mdash; rice, pasta, and skillet bases that only need what&#8217;s already in the fridge.
      </div>
    </div>
"""
chapter_opener_image = """
    <div class="img-placeholder" style="position:absolute; top:calc(-1 * var(--bleed)); bottom:calc(-1 * var(--bleed)); right:calc(-1 * var(--bleed)); left:38%;">
      <div class="ph-inner">
        <div class="ph-caption">Photography placeholder &mdash; overhead flat-lay: 4&ndash;5 labeled glass<br>pantry jars filled with dry rice / pasta mixes, kraft labels,<br>light wood surface, soft natural window light, shallow props<br>(measuring spoon, linen napkin). Full-bleed, warm &amp; editorial.</div>
      </div>
    </div>
"""
html_out = f"""<!doctype html>
<html><head><meta charset="utf-8"><link rel="stylesheet" href="../tokens.css"></head>
<body>
<div class="page guides page-right">
  <div class="trim-line"></div>
  <span class="label-tag">CHAPTER OPENER (recto — no running head / no folio)</span>
  {chapter_opener_image}
  <div class="content">
    {chapter_opener_body}
  </div>
</div>
</body></html>"""
open("/home/user/Formattazione-Ross/design/sample/1-chapter-opener.html", "w").write(html_out)

# ---------------------------------------------------------------------------
# 2 & 3. NORMAL RECIPE PAGES
# ---------------------------------------------------------------------------
def normal_recipe_page(title, side, tag, folio_num, rh_text, out_path, thumb_caption):
    r = get(title)
    add_html = ""
    if add_ingredients(r):
        add_html = f'''<div class="section-label alt" style="margin-top:16px;">What to Add</div>
        <ul class="add-list">{ingredient_block(add_ingredients(r))}</ul>'''
    body = f"""
    <div class="recipe-eyebrow">Chapter 1 &middot; Recipe {r['order']:02d}</div>
    <div class="recipe-title" style="margin-top:6px;">{esc(r['title'])}</div>
    <div class="recipe-intro" style="margin-top:10px; max-width:5.6in;">{esc(r['intro'])}</div>
    <div style="margin-top:16px;">{meta_row(r)}</div>
    <hr class="divider">
    <div style="display:flex; gap:0.5in; margin-top:4px;">
      <div style="flex: 0 0 2.55in;">
        <div class="section-label">{jar_label(r)}</div>
        <ul class="ingredient-list">{ingredient_block(jar_ingredients(r))}</ul>
        {add_html}
        <div class="img-placeholder" style="margin-top:16px; height:1.5in; border-radius:2px;">
          <div class="ph-inner"><div class="ph-caption">{thumb_caption}</div></div>
        </div>
      </div>
      <div style="flex:1;">
        <div class="section-label">Instructions</div>
        <ol class="instructions">{instructions_block(r['fields'].get('instructions', []))}</ol>
        <div style="display:flex; gap:14px; margin-top:18px;">
          <div style="flex:1;">{nutrition_html(r)}</div>
          <div style="flex:1;">{storage_html(r)}</div>
        </div>
      </div>
    </div>
    """
    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><link rel="stylesheet" href="../tokens.css"></head>
<body>
<div class="page guides {side}">
  <div class="trim-line"></div>
  <div class="safe-line"></div>
  <span class="label-tag">{tag}</span>
  <div class="running-head">{esc(rh_text)}</div>
  <div class="folio">{folio_num}</div>
  <div class="content">{body}</div>
</div>
</body></html>"""
    open(out_path, "w").write(page)

normal_recipe_page(
    "Cheesy Scalloped Potato Mix", "page-left",
    "NORMAL RECIPE PAGE 1 (verso)", 24,
    "Chapter One · Meal-Ready Dry Mixes",
    "/home/user/Formattazione-Ross/design/sample/2-recipe-normal-1.html",
    "Photography placeholder &mdash; small jar of pale cheese-sauce mix, wood surface",
)
normal_recipe_page(
    "Taco and Burrito Bowl Seasoning Kit", "page-right",
    "NORMAL RECIPE PAGE 2 (recto)", 29,
    "Taco & Burrito Bowl Seasoning Kit",
    "/home/user/Formattazione-Ross/design/sample/3-recipe-normal-2.html",
    "Photography placeholder &mdash; jar of red-toned rice seasoning mix, overhead",
)

# ---------------------------------------------------------------------------
# 4. IMAGE-HEAVY RECIPE PAGE (Rice Pilaf Mix -- fewer text fields)
# ---------------------------------------------------------------------------
r = get("Rice Pilaf Mix")
body = f"""
    <div class="img-placeholder" style="position:absolute; top:calc(-1 * var(--bleed)); left:calc(-1 * var(--bleed)); right:calc(-1 * var(--bleed)); height:5.6in;">
      <div class="ph-inner">
        <div class="ph-caption">Photography placeholder &mdash; full-bleed hero: finished rice pilaf in a rustic<br>bowl, steam visible, wooden spoon resting alongside, labeled pantry jar<br>of the dry mix just in frame. Warm natural light, shallow depth of field.</div>
      </div>
    </div>
    <div style="position:absolute; top:5.85in; left:0; right:0;">
      <div class="recipe-eyebrow">Chapter 1 &middot; Recipe 01</div>
      <div class="recipe-title" style="margin-top:6px;">{esc(r['title'])}</div>
      <div class="recipe-intro" style="margin-top:8px; max-width:5.8in;">{esc(r['intro'])}</div>
      <div style="margin-top:12px;">{meta_row(r)}</div>
      <hr class="divider" style="margin:12px 0;">
      <div style="display:flex; gap:0.55in;">
        <div style="flex:1;">
          <div class="section-label">Ingredients</div>
          <ul class="ingredient-list">{ingredient_block(jar_ingredients(r))}</ul>
        </div>
        <div style="flex:1;">
          <div class="section-label">Instructions</div>
          <ol class="instructions">{instructions_block(r['fields'].get('instructions', []))}</ol>
          <div style="margin-top:14px;">{storage_html(r)}</div>
        </div>
      </div>
    </div>
"""
page = f"""<!doctype html>
<html><head><meta charset="utf-8"><link rel="stylesheet" href="../tokens.css"></head>
<body>
<div class="page guides page-left">
  <div class="trim-line"></div>
  <span class="label-tag">IMAGE-HEAVY RECIPE PAGE (verso) &mdash; running head dropped: bled photo occupies that zone. No nutrition field in source, correctly omitted.</span>
  <div class="folio">18</div>
  <div class="content" style="top:0; bottom:calc(var(--bleed) + var(--margin-bottom));">{body}</div>
</div>
</body></html>"""
open("/home/user/Formattazione-Ross/design/sample/4-recipe-image-heavy.html", "w").write(page)

# ---------------------------------------------------------------------------
# 5. TEXT-HEAVY RECIPE PAGE (Chicken Fajita Rice Bowl Mix -- most content)
# ---------------------------------------------------------------------------
r = get("Chicken Fajita Rice Bowl Mix")
body = f"""
    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
      <div style="max-width:4.6in;">
        <div class="recipe-eyebrow">Chapter 1 &middot; Recipe 19</div>
        <div class="recipe-title long" style="margin-top:6px;">{esc(r['title'])}</div>
        <div class="recipe-intro" style="margin-top:8px;">{esc(r['intro'])}</div>
      </div>
      <div class="img-placeholder" style="width:1.9in; height:1.9in; flex:0 0 auto; border-radius:2px;">
        <div class="ph-inner"><div class="ph-caption">Placeholder &mdash; fajita rice bowl, overhead</div></div>
      </div>
    </div>
    <div style="margin-top:14px;">{meta_row(r)}</div>
    <hr class="divider" style="margin:12px 0;">
    <div style="display:flex; gap:0.5in;">
      <div style="flex: 0 0 2.55in;">
        <div class="section-label">{jar_label(r)}</div>
        <ul class="ingredient-list">{ingredient_block(jar_ingredients(r))}</ul>
        <div class="section-label alt" style="margin-top:14px;">What to Add</div>
        <ul class="add-list">{ingredient_block(add_ingredients(r))}</ul>
      </div>
      <div style="flex:1;">
        <div class="section-label">Instructions</div>
        <ol class="instructions">{instructions_block(r['fields'].get('instructions', []))}</ol>
      </div>
    </div>
    <div style="display:flex; gap:14px; margin-top:14px;">
      <div style="flex:1;">{nutrition_html(r)}</div>
      <div style="flex:1;">{storage_html(r)}</div>
    </div>
"""
page = f"""<!doctype html>
<html><head><meta charset="utf-8"><link rel="stylesheet" href="../tokens.css"></head>
<body>
<div class="page guides page-right">
  <div class="trim-line"></div>
  <div class="safe-line"></div>
  <span class="label-tag">TEXT-HEAVY RECIPE PAGE (recto) &mdash; densest recipe in Ch.1, all fields present</span>
  <div class="running-head">Chicken Fajita Rice Bowl Mix</div>
  <div class="folio">19</div>
  <div class="content">{body}</div>
</div>
</body></html>"""
open("/home/user/Formattazione-Ross/design/sample/5-recipe-text-heavy.html", "w").write(page)

print("done")
