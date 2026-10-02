"""Minimal IDML (InDesign Markup Language) writer.

Writes a complete InDesign package (.idml) from a page plan: master spreads,
spreads with pages and threaded text frames, stories with paragraph/character
style ranges, inline (anchored) graphics, text variables, sections and swatches.
Static resources (preferences, default styles, cross-reference formats...) come
from `template/`, which is an InDesign-exported IDML unpacked; this module only
patches it.  InDesign opens the result with File > Open and saves it as .indd.

Coordinates: everything is in points.  Page coordinates (x from the page's left
edge, y from its top) are converted to spread coordinates, where the origin is
the binding (spine) at the vertical centre of the spread.
"""
import shutil
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "template"
DOM = "10.0"
PKG = 'xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"'
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
LAYER = "uLayer1"

NO_CHAR = "CharacterStyle/$ID/[No character style]"
PAGE = "\x00PAGE\x00"          # placeholder for the current page number


def a(v):
    return quoteattr(str(v))


def num(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# stories
# ---------------------------------------------------------------------------
class Story:
    """Builds the XML of one story: a list of paragraphs, each a list of runs.
    A run is (text, char_style, attrs) or an inline graphic dict."""

    def __init__(self, doc, sid):
        self.doc = doc
        self.sid = sid
        self.paras = []

    def para(self, style, runs, **attrs):
        self.paras.append((style, runs, attrs))

    def xml(self):
        out = [XML_HEAD, f'<idPkg:Story {PKG} DOMVersion="{DOM}">',
               f'<Story Self={a(self.sid)} AppliedTOCStyle="n" TrackChanges="false" '
               'StoryTitle="$ID/" AppliedNamedGrid="n">',
               '<StoryPreference OpticalMarginAlignment="false" OpticalMarginSize="12" '
               'FrameType="TextFrameType" StoryOrientation="Horizontal" '
               'StoryDirection="LeftToRightDirection"/>',
               '<InCopyExportOption IncludeGraphicProxies="true" IncludeAllResources="false"/>']
        for i, (style, runs, attrs) in enumerate(self.paras):
            pattrs = "".join(f" {k}={a(v)}" for k, v in attrs.items()
                             if not k.startswith("_") and k != "Leading")
            out.append(f'<ParagraphStyleRange AppliedParagraphStyle={a("ParagraphStyle/" + style)}{pattrs}>')
            if "Leading" in attrs:
                out.append(f'<Properties><Leading type="unit">{num(attrs["Leading"])}</Leading></Properties>')
            last = i == len(self.paras) - 1
            if not runs:
                runs = [("", None, {})]
            for j, run in enumerate(runs):
                br = "" if (last or j < len(runs) - 1) else "<Br/>"
                if isinstance(run, dict):           # inline graphic
                    out.append(f'<CharacterStyleRange AppliedCharacterStyle={a(NO_CHAR)}>'
                               f'{self.doc.inline_graphic(run)}{br}</CharacterStyleRange>')
                    continue
                text, cstyle, cattrs = run
                cs = "CharacterStyle/" + cstyle if cstyle else NO_CHAR
                cat = "".join(f" {k}={a(v)}" for k, v in (cattrs or {}).items() if k != "_variable")
                if cattrs and cattrs.get("_variable"):
                    body = self.doc.variable_instance(cattrs["_variable"])
                else:
                    # the current-page-number marker is an InDesign processing instruction
                    parts = text.split(PAGE)
                    body = ""
                    for k, part in enumerate(parts):
                        if part:
                            body += f"<Content>{escape(part)}</Content>"
                        if k < len(parts) - 1:
                            body += "<Content><?ACE 18?></Content>"
                out.append(f"<CharacterStyleRange AppliedCharacterStyle={a(cs)}{cat}>{body}{br}</CharacterStyleRange>")
            out.append("</ParagraphStyleRange>")
        out.append("</Story></idPkg:Story>")
        return "\n".join(out)


# ---------------------------------------------------------------------------
# document
# ---------------------------------------------------------------------------
class Document:
    def __init__(self, page_w, page_h, facing=True):
        self.W, self.H = page_w, page_h
        self.facing = facing
        self.n = 0
        self.stories = {}
        self.masters = []        # (sid, name_prefix, base_name, [page_items_left], [page_items_right])
        self.pages = []          # dicts: master, items(list of xml producers)
        self.sections = []       # (first_page_index, style, start)
        self.variables = []      # (name, paragraph_style)
        self.links = {}          # image file -> path on disk
        self.colors = []         # (name, cmyk tuple)
        self.par_styles = []     # xml strings
        self.char_styles = []
        self.var_ids = {}

    def uid(self, prefix="u"):
        self.n += 1
        return f"{prefix}{self.n:x}"

    # ----- stories, frames, graphics -----
    def story(self):
        sid = self.uid("st")
        s = Story(self, sid)
        self.stories[sid] = s
        return s

    def spread_xy(self, page_index_in_spread_side, x, y):
        """page coords -> spread coords; side 'L' (left page) or 'R' (right)."""
        if page_index_in_spread_side == "L":
            return x - self.W, y - self.H / 2
        return x, y - self.H / 2

    def frame_xml(self, side, story, prev, nxt, box, fid, first_baseline="LeadingOffset",
                  valign="TopAlign"):
        x0, y0, x1, y1 = box
        X0, Y0 = self.spread_xy(side, x0, y0)
        X1, Y1 = self.spread_xy(side, x1, y1)
        pts = "".join(
            f'<PathPointType Anchor="{num(px)} {num(py)}" LeftDirection="{num(px)} {num(py)}" '
            f'RightDirection="{num(px)} {num(py)}"/>'
            for px, py in ((X0, Y0), (X0, Y1), (X1, Y1), (X1, Y0)))
        return (f'<TextFrame Self={a(fid)} ParentStory={a(story)} PreviousTextFrame={a(prev or "n")} '
                f'NextTextFrame={a(nxt or "n")} ContentType="TextType" ItemLayer="{LAYER}" '
                'AppliedObjectStyle="ObjectStyle/$ID/[Normal Text Frame]" Visible="true" Name="$ID/" '
                'Locked="false" FillColor="Swatch/None" StrokeColor="Swatch/None" StrokeWeight="0" '
                'ItemTransform="1 0 0 1 0 0">'
                f'<Properties><PathGeometry><GeometryPathType PathOpen="false"><PathPointArray>{pts}'
                '</PathPointArray></GeometryPathType></PathGeometry></Properties>'
                f'<TextFramePreference TextColumnCount="1" TextColumnFixedWidth="{num(x1 - x0)}" '
                f'UseFixedColumnWidth="false" FirstBaselineOffset="{first_baseline}" '
                f'MinimumFirstBaselineOffset="0" VerticalJustification="{valign}" VerticalThreshold="0" '
                'IgnoreWrap="false" AutoSizingType="Off" AutoSizingReferencePoint="CenterPoint">'
                '<Properties><InsetSpacing type="list"><ListItem type="unit">0</ListItem>'
                '<ListItem type="unit">0</ListItem><ListItem type="unit">0</ListItem>'
                '<ListItem type="unit">0</ListItem></InsetSpacing></Properties>'
                '</TextFramePreference></TextFrame>')

    def line_xml(self, side, x0, y, x1, weight, color):
        X0, Y = self.spread_xy(side, x0, y)
        X1, _ = self.spread_xy(side, x1, y)
        pts = "".join(
            f'<PathPointType Anchor="{num(px)} {num(Y)}" LeftDirection="{num(px)} {num(Y)}" '
            f'RightDirection="{num(px)} {num(Y)}"/>' for px in (X0, X1))
        return (f'<GraphicLine Self={a(self.uid("gl"))} ItemLayer="{LAYER}" StrokeWeight="{num(weight)}" '
                f'StrokeColor={a(color)} FillColor="Swatch/None" '
                'AppliedObjectStyle="ObjectStyle/$ID/[None]" Visible="true" Name="$ID/" ItemTransform="1 0 0 1 0 0">'
                f'<Properties><PathGeometry><GeometryPathType PathOpen="true"><PathPointArray>{pts}'
                '</PathPointArray></GeometryPathType></PathGeometry></Properties></GraphicLine>')

    def inline_graphic(self, g):
        """g: {file, path, w, h, px_w, px_h} -> anchored inline Rectangle with Image."""
        w, h = g["w"], g["h"]
        self.links[g["file"]] = g["path"]
        rid, iid, lid = self.uid("rc"), self.uid("im"), self.uid("ln")
        pts = "".join(
            f'<PathPointType Anchor="{num(px)} {num(py)}" LeftDirection="{num(px)} {num(py)}" '
            f'RightDirection="{num(px)} {num(py)}"/>'
            for px, py in ((0, 0), (0, h), (w, h), (w, 0)))
        sx, sy = w / g["px_w"], h / g["px_h"]
        fmt = "$ID/Portable Network Graphics (PNG)"
        return (f'<Rectangle Self={a(rid)} ContentType="GraphicType" StoryTitle="$ID/" ItemLayer="{LAYER}" '
                'StrokeWeight="0" StrokeColor="Swatch/None" FillColor="Swatch/None" '
                'AppliedObjectStyle="ObjectStyle/$ID/[None]" Visible="true" Name="$ID/" ItemTransform="1 0 0 1 0 0">'
                f'<Properties><PathGeometry><GeometryPathType PathOpen="false"><PathPointArray>{pts}'
                '</PathPointArray></GeometryPathType></PathGeometry></Properties>'
                '<AnchoredObjectSetting AnchoredPosition="InlinePosition" SpineRelative="false" '
                'LockPosition="false" PinPosition="true" AnchorXoffset="0" AnchorYoffset="0"/>'
                '<FrameFittingOption AutoFit="false" LeftCrop="0" TopCrop="0" RightCrop="0" BottomCrop="0" '
                'FittingOnEmptyFrame="Proportionally" FittingAlignment="CenterAnchor"/>'
                f'<Image Self={a(iid)} Space="$ID/#Links_RGB" ActualPpi="72 72" '
                f'EffectivePpi="{round(72 / sx)} {round(72 / sy)}" ImageRenderingIntent="UseColorSettings" '
                'LocalDisplaySetting="Default" ImageTypeName="$ID/Portable Network Graphics (PNG)" '
                'AppliedObjectStyle="ObjectStyle/$ID/[None]" Visible="true" Name="$ID/" '
                f'ItemTransform="{num(sx)} 0 0 {num(sy)} 0 0">'
                '<Properties><Profile type="string">$ID/None</Profile>'
                f'<GraphicBounds Left="0" Top="0" Right="{g["px_w"]}" Bottom="{g["px_h"]}"/></Properties>'
                f'<Link Self={a(lid)} AssetURL="$ID/" AssetID="$ID/" '
                f'LinkResourceURI={a("file:Links/" + g["file"])} LinkResourceFormat={a(fmt)} '
                'StoredState="Normal" LinkClassID="35906" LinkClientID="257" LinkResourceModified="false" '
                'LinkObjectModified="false" ShowInUI="true" CanEmbed="true" CanUnembed="true" '
                'CanPackage="true" ImportPolicy="NoAutoImport" ExportPolicy="NoAutoExport"/>'
                '</Image></Rectangle>')

    def add_variable(self, name, paragraph_style):
        vid = "dTextVariablen" + name
        self.variables.append((vid, name, paragraph_style))
        self.var_ids[name] = vid
        return name

    def variable_instance(self, name):
        return (f'<TextVariableInstance Self={a(self.uid("tv"))} Name={a(name)} ResultText="" '
                f'AssociatedTextVariable={a(self.var_ids[name])}/>')

    # ----- styles -----
    def paragraph_style(self, name, based="$ID/NormalParagraphStyle", font=None, tabs=None, **attrs):
        props = f'<BasedOn type="string">{escape(based)}</BasedOn>'
        if font:
            props += f'<AppliedFont type="string">{escape(font)}</AppliedFont>'
        if "Leading" in attrs:
            props += f'<Leading type="unit">{num(attrs.pop("Leading"))}</Leading>'
        if "BalanceRaggedLines" in attrs:
            props += f'<BalanceRaggedLines type="enumeration">{attrs.pop("BalanceRaggedLines")}</BalanceRaggedLines>'
        for key in ("RuleBelowColor", "RuleAboveColor"):
            if key in attrs:
                props += f'<{key} type="object">{escape(attrs.pop(key))}</{key}>'
        if tabs:
            items = "".join(
                f'<ListItem type="record"><Alignment type="enumeration">{al}</Alignment>'
                '<AlignmentCharacter type="string">.</AlignmentCharacter>'
                f'<Leader type="string">{escape(ld)}</Leader><Position type="unit">{num(pos)}</Position></ListItem>'
                for al, pos, ld in tabs)
            props += f'<TabList type="list">{items}</TabList>'
        at = "".join(f" {k}={a(v)}" for k, v in attrs.items())
        self.par_styles.append(
            f'<ParagraphStyle Self={a("ParagraphStyle/" + name)} Name={a(name)} Imported="false" '
            f'NextStyle={a("ParagraphStyle/" + name)} KeyboardShortcut="0 0"{at}>'
            f'<Properties>{props}<PreviewColor type="enumeration">Nothing</PreviewColor></Properties>'
            '</ParagraphStyle>')

    def character_style(self, name, font=None, **attrs):
        props = '<BasedOn type="string">$ID/[No character style]</BasedOn>'
        if font:
            props += f'<AppliedFont type="string">{escape(font)}</AppliedFont>'
        at = "".join(f" {k}={a(v)}" for k, v in attrs.items())
        self.char_styles.append(
            f'<CharacterStyle Self={a("CharacterStyle/" + name)} Imported="false" KeyboardShortcut="0 0" '
            f'Name={a(name)}{at}><Properties>{props}<PreviewColor type="enumeration">Nothing</PreviewColor>'
            '</Properties></CharacterStyle>')

    def color(self, name, cmyk):
        self.colors.append((name, cmyk))
        return "Color/" + name

    # ----- pages -----
    def master(self, prefix, base, left_items, right_items):
        mid = self.uid("ms")
        self.masters.append((mid, prefix, base, left_items, right_items))
        return mid

    def page(self, master=None):
        p = {"master": master, "items": [], "id": self.uid("pg")}
        self.pages.append(p)
        return p

    def section(self, page_index, style, start):
        self.sections.append((page_index, style, start))

    def side(self, i):
        if not self.facing:
            return "R"
        return "R" if i % 2 == 0 else "L"

    # ----- writing -----
    def _spreads(self):
        """Group pages into spreads: [p0] then pairs (L,R)."""
        if not self.facing:
            return [[i] for i in range(len(self.pages))]
        groups = [[0]]
        i = 1
        while i < len(self.pages):
            groups.append(list(range(i, min(i + 2, len(self.pages)))))
            i += 2
        return groups

    def _page_xml(self, p, side, name, master_id):
        tx = -self.W if side == "L" else 0
        mt = master_id or "n"
        margins = p.get("margins", (0, 0, 0, 0))
        return (f'<Page Self={a(p["id"])} GeometricBounds="0 0 {num(self.H)} {num(self.W)}" '
                f'ItemTransform="1 0 0 1 {num(tx)} {num(-self.H / 2)}" Name={a(name)} '
                f'AppliedTrapPreset="TrapPreset/$ID/kDefaultTrapStyleName" OverrideList="" '
                f'AppliedMaster={a(mt)} MasterPageTransform="1 0 0 1 0 0" TabOrder="" '
                'GridStartingPoint="TopOutside" UseMasterGrid="true">'
                '<Properties><PageColor type="enumeration">UseMasterColor</PageColor></Properties>'
                f'<MarginPreference ColumnCount="1" ColumnGutter="12" Top="{num(margins[0])}" '
                f'Bottom="{num(margins[2])}" Left="{num(margins[3])}" Right="{num(margins[1])}" '
                'ColumnDirection="Horizontal"/></Page>')

    def write(self, out_path, page_margins, doc_name):
        out_path = Path(out_path)
        work = out_path.with_suffix(".build")
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(TEMPLATE, work)
        for sub in ("Spreads", "MasterSpreads", "Stories"):
            shutil.rmtree(work / sub, ignore_errors=True)
            (work / sub).mkdir()

        # --- master spreads
        master_refs = []
        for mid, prefix, base, left_items, right_items in self.masters:
            pages_xml = []
            items_xml = []
            sides = [("L", left_items), ("R", right_items)] if self.facing else [("R", right_items)]
            for side, items in sides:
                pid = self.uid("mp")
                tx = -self.W if side == "L" else 0
                m = page_margins(side)
                pages_xml.append(
                    f'<Page Self={a(pid)} GeometricBounds="0 0 {num(self.H)} {num(self.W)}" '
                    f'ItemTransform="1 0 0 1 {num(tx)} {num(-self.H / 2)}" Name={a(prefix)} '
                    'AppliedTrapPreset="TrapPreset/$ID/kDefaultTrapStyleName" OverrideList="" '
                    'AppliedMaster="n" MasterPageTransform="1 0 0 1 0 0" TabOrder="" '
                    'GridStartingPoint="TopOutside" UseMasterGrid="true">'
                    '<Properties><PageColor type="enumeration">UseMasterColor</PageColor></Properties>'
                    f'<MarginPreference ColumnCount="1" ColumnGutter="12" Top="{num(m[0])}" Bottom="{num(m[2])}" '
                    f'Left="{num(m[3])}" Right="{num(m[1])}" ColumnDirection="Horizontal"/></Page>')
                for item in items:
                    items_xml.append(item(side))
            name = f"{prefix}-{base}"
            xml = (XML_HEAD + f'<idPkg:MasterSpread {PKG} DOMVersion="{DOM}">'
                   f'<MasterSpread Self={a(mid)} ItemTransform="1 0 0 1 0 0" OverriddenPageItemProps="" '
                   f'Name={a(name)} NamePrefix={a(prefix)} BaseName={a(base)} ShowMasterItems="true" '
                   f'PageCount="{len(sides)}" PrimaryTextFrame="n">'
                   '<Properties><PageColor type="enumeration">UseMasterColor</PageColor></Properties>'
                   + "".join(pages_xml) + "".join(items_xml) + "</MasterSpread></idPkg:MasterSpread>")
            (work / "MasterSpreads" / f"MasterSpread_{mid}.xml").write_text(xml, encoding="utf-8")
            master_refs.append(f'<idPkg:MasterSpread src="MasterSpreads/MasterSpread_{mid}.xml"/>')

        # --- spreads
        spread_refs = []
        for grp in self._spreads():
            sid = self.uid("sp")
            pages_xml, items_xml = [], []
            for i in grp:
                p = self.pages[i]
                side = self.side(i)
                p["margins"] = page_margins(side)
                pages_xml.append(self._page_xml(p, side, str(i + 1), p["master"]))
                for item in p["items"]:
                    items_xml.append(item(side))
            binding = 0 if (self.facing and grp == [0]) else (1 if self.facing and len(grp) == 2 else 0)
            if self.facing and len(grp) == 1 and grp != [0]:
                binding = 1          # a lone left page at the end of the book
            xml = (XML_HEAD + f'<idPkg:Spread {PKG} DOMVersion="{DOM}">'
                   f'<Spread Self={a(sid)} FlattenerOverride="Default" AllowPageShuffle="true" '
                   f'ItemTransform="1 0 0 1 0 0" ShowMasterItems="true" PageCount="{len(grp)}" '
                   f'BindingLocation="{binding}" PageTransitionType="None" '
                   'PageTransitionDirection="NotApplicable" PageTransitionDuration="Medium">'
                   + "".join(pages_xml) + "".join(items_xml) + "</Spread></idPkg:Spread>")
            (work / "Spreads" / f"Spread_{sid}.xml").write_text(xml, encoding="utf-8")
            spread_refs.append(f'<idPkg:Spread src="Spreads/Spread_{sid}.xml"/>')

        # --- stories
        story_refs = []
        for sid, st in self.stories.items():
            (work / "Stories" / f"Story_{sid}.xml").write_text(st.xml(), encoding="utf-8")
            story_refs.append(f'<idPkg:Story src="Stories/Story_{sid}.xml"/>')

        # --- styles, swatches, preferences, designmap
        self._patch_styles(work)
        self._patch_graphic(work)
        self._patch_preferences(work)
        self._write_designmap(work, master_refs, spread_refs, story_refs, doc_name)

        # --- package (mimetype first, uncompressed)
        if out_path.exists():
            out_path.unlink()
        with zipfile.ZipFile(out_path, "w") as z:
            z.write(work / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
            for f in sorted(work.rglob("*")):
                if f.is_file() and f.name != "mimetype":
                    z.write(f, f.relative_to(work).as_posix(), compress_type=zipfile.ZIP_DEFLATED)
        shutil.rmtree(work)

        links = out_path.parent / "Links"
        links.mkdir(exist_ok=True)
        for name, src in self.links.items():
            shutil.copy(src, links / name)

    def _patch_styles(self, work):
        f = work / "Resources" / "Styles.xml"
        s = f.read_text(encoding="utf-8")
        s = s.replace("</RootCharacterStyleGroup>", "".join(self.char_styles) + "</RootCharacterStyleGroup>")
        s = s.replace("</RootParagraphStyleGroup>", "".join(self.par_styles) + "</RootParagraphStyleGroup>")
        f.write_text(s, encoding="utf-8")

    def _patch_graphic(self, work):
        f = work / "Resources" / "Graphic.xml"
        s = f.read_text(encoding="utf-8")
        add = "".join(
            f'<Color Self={a("Color/" + n)} Model="Process" Space="CMYK" ColorValue="{" ".join(map(str, v))}" '
            f'ColorOverride="Normal" AlternateSpace="NoAlternateColor" AlternateColorValue="" Name={a(n)} '
            'ColorEditable="true" ColorRemovable="true" Visible="true" SwatchCreatorID="7937"/>'
            for n, v in self.colors)
        i = s.index("<Color ")
        f.write_text(s[:i] + add + s[i:], encoding="utf-8")

    def _patch_preferences(self, work):
        import re
        f = work / "Resources" / "Preferences.xml"
        s = f.read_text(encoding="utf-8")

        def setattr_(tag, key, value):
            nonlocal s
            m = re.search(rf"<{tag} [^>]*>", s)
            t = m.group(0)
            if re.search(rf' {key}="[^"]*"', t):
                t2 = re.sub(rf' {key}="[^"]*"', f" {key}={a(value)}", t)
            else:
                t2 = t.replace(f"<{tag} ", f"<{tag} {key}={a(value)} ", 1)
            s = s.replace(t, t2, 1)

        setattr_("DocumentPreference", "PageHeight", num(self.H))
        setattr_("DocumentPreference", "PageWidth", num(self.W))
        setattr_("DocumentPreference", "PagesPerDocument", len(self.pages))
        setattr_("DocumentPreference", "FacingPages", "true" if self.facing else "false")
        setattr_("TextPreference", "SmartTextReflow", "false")
        f.write_text(s, encoding="utf-8")

    def _write_designmap(self, work, master_refs, spread_refs, story_refs, doc_name):
        import re
        f = work / "designmap.xml"
        s = f.read_text(encoding="utf-8")
        story_ids = " ".join(list(self.stories) + ["uBacking"])
        s = re.sub(r'StoryList="[^"]*"', f'StoryList="{story_ids}"', s, count=1)
        s = re.sub(r'ActiveLayer="[^"]*"', f'ActiveLayer="{LAYER}"', s, count=1)
        s = re.sub(r'DOMVersion="[^"]*"', f'DOMVersion="{DOM}"', s, count=1)
        # language used by the styles
        if "English%3a USA" not in s:
            s = s.replace('<idPkg:Graphic', '<Language Self="Language/$ID/English%3a USA" '
                          'Name="$ID/English: USA" SingleQuotes="‘’" DoubleQuotes="“”" '
                          'PrimaryLanguageName="$ID/English" SublanguageName="$ID/USA" Id="269" '
                          'HyphenationVendor="Proximity" SpellingVendor="Proximity" />\n\t<idPkg:Graphic', 1)
        # text variables
        tv = "".join(
            f'<TextVariable Self={a(vid)} Name={a(name)} VariableType="MatchParagraphStyleType">'
            f'<MatchParagraphStylePreference TextBefore="" TextAfter="" '
            f'AppliedParagraphStyle={a("ParagraphStyle/" + pstyle)} SearchStrategy="FirstOnPage" '
            'ChangeCase="None" DeleteEndPunctuation="false"/></TextVariable>'
            for vid, name, pstyle in self.variables)
        s = s.replace("<idPkg:Tags", tv + "<idPkg:Tags", 1)
        # layers, master spreads, spreads and sections sit together, in this
        # order, where the template's layers were
        start = s.index("<Layer ")
        s = re.sub(r"<Layer .*?</Layer>\s*", "", s, flags=re.S)
        s = re.sub(r"<idPkg:MasterSpread [^>]*/>\s*", "", s)
        s = re.sub(r"<idPkg:Spread [^>]*/>\s*", "", s)
        s = re.sub(r"<idPkg:Story [^>]*/>\s*", "", s)
        s = re.sub(r"<Section .*?</Section>\s*", "", s, flags=re.S)
        layer = (f'<Layer Self="{LAYER}" Name="Layer 1" Visible="true" Locked="false" IgnoreWrap="false" '
                 'ShowGuides="true" LockGuides="false" UI="true" Expendable="true" Printable="true">'
                 '<Properties><LayerColor type="enumeration">LightBlue</LayerColor></Properties></Layer>')
        sections = []
        for k, (pi, style, start_no) in enumerate(self.sections):
            nxt = self.sections[k + 1][0] if k + 1 < len(self.sections) else len(self.pages)
            sections.append(
                f'<Section Self={a(self.uid("sc"))} Length="{nxt - pi}" Name="" ContinueNumbering="false" '
                f'IncludeSectionPrefix="false" Marker="" PageStart={a(self.pages[pi]["id"])} '
                f'PageNumberStart="{start_no}" SectionPrefix="">'
                f'<Properties><PageNumberStyle type="enumeration">{style}</PageNumberStyle></Properties></Section>')
        block = layer + "\n".join(master_refs + spread_refs + sections) + "\n"
        s = s[:start] + block + s[start:]
        s = s.replace('<idPkg:BackingStory src="XML/BackingStory.xml" />',
                      '<idPkg:BackingStory src="XML/BackingStory.xml" />' + "".join(story_refs), 1)
        f.write_text(s, encoding="utf-8")
