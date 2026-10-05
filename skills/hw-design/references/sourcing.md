# Sourcing: verifying a part number and stock from a script

How to establish that a distributor part number exists, matches the intended
part, and is in stock, when web search is unavailable or rate-limited. Load this
at phase 1 and in `/hw-bom`, before writing an `lcsc`, `digikey`, or `mouser` key
into `design.py`.

Source: the mic run's passives and active-parts scout
(`hypercardiod_mic/lib/research/passives-active.md`, 2026-10-03, sections 2, 6
and 8) and its off-board connector scout (`offboard-connectors.md`, availability
table), plus the run's query scripts where those notes omit a URL. The recorded
status codes (403 from LCSC search, 404 from one Yageo URL) are from one machine
on 2026-10-03 and can change.

A distributor part number copied from a search result is a claim. A number read
back from a detail endpoint and matched on model, brand and package is a
verified fact. Record which one a `design.py` key is.

## 1. Find candidates: JLCPCB parts search

JLCPCB's public parts search answers a `selectSmtComponentList` POST request
with candidate parts and their LCSC numbers. The run used it to find candidate
LCSC numbers for 25 reference designators (16 distinct LCSC numbers) after
LCSC's own search refused the machine (section 3).

- Use it for candidates only. A search hit lists a model and a number, and
  searches match loosely on the name.
- The project's research notes name only "JLCPCB's public parts search". The
  run's query script recorded the request:

  ```
  POST https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList
  Content-Type: application/json
  {"keyword": "<text>", "currentPage": 1, "pageSize": 10, "searchSource": "search"}
  ```

  Candidates are in `data.componentPageInfo.list`. This is an undocumented
  endpoint seen in one run (needs-verification): if it fails, read the current
  request from JLCPCB's parts-library page in a browser.
- Verify every candidate in section 2 before it enters `design.py`.

## 2. Verify: LCSC product detail

One call returns model, brand, package and stock for one LCSC number:

```
https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=<C number>
```

The run read all 25 reference designators (16 distinct LCSC numbers) this way.
The URL above is recorded in `passives-active.md` section 2. The run's script
sent a GET with a browser user agent and read the JSON `result` object; that
request shape is recorded only in the script (needs-verification). The run
accepted a number only when the returned model, brand and package matched the
intended part. Fields to record
per part: model, brand, package, stock, minimum order, and the retrieval date.

Observed behaviours worth recording, because they change what a number means:

| Observation | Source |
|---|---|
| A reel part had stock 178090 while the tube part of the same die was obsolete at the maker | passives-active.md section 2, U1 |
| A bulk-packed 47 uF part showed stock 5, then 0, within one session; the taped-packing listing of the same part had 1830 | passives-active.md section 2 and 6 |
| Stock is per listing, so two listings of one electrical part carry different stock | same |

Stock moves. Write the stock and the date it was read, and treat a stock under
the quantity per board times the build count as a finding.

## 3. LCSC search returns HTTP 403

LCSC's search endpoint returned HTTP 403 ("edge access denied") to the run's
machine. The run notes do not record its URL. The detail endpoint on
wmsc.lcsc.com (section 2) was not refused: it answered for all 16 numbers. Do
not bypass the 403. Use section 1 to find the number and section 2 to
verify it. State in the report that the LCSC search was refused.

## 4. Mouser and DigiKey: bot checks

Mouser and DigiKey pages and Mouser-hosted datasheet mirrors returned an HTML
bot-check page where a PDF or listing was expected. The run read no stock from
either.

- Record the part as NOT-MACHINE-RETRIEVABLE (`agents/resource-scout.md`):
  asset exists, last mile blocked.
- Give the exact URL for a person to open in a browser, and state what to read
  from it (stock, price, datasheet).
- Do not write a `digikey` or `mouser` key whose number was not read back. The
  run omitted both keys for all 25 reference designators for this reason.
- A listing seen in a search result confirms the part exists. It does not
  confirm stock.

Measured instance: the Olimex GX16-4 datasheet hosted on Mouser returned a bot
check; DigiKey listed product 19204167 behind a bot check and stock was not read
(`offboard-connectors.md`, availability table).

## 5. Dead datasheet URLs: Wayback CDX

When a manufacturer URL returns 404, look the URL up in the Internet Archive's
CDX index to list its snapshots
([CDX server API](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server)),
then fetch a snapshot.

The run's instance: Yageo's MFR datasheet URL returned 404 after the site moved
to yageogroup.com. The run read snapshot 20240921175854 from web.archive.org.
The run notes record the snapshot, not whether the CDX index found it.

Then compare bytes against a distributor's copy of the same datasheet. `cmp` on
the snapshot and LCSC's datasheet copy for C1519255 reported identical bytes,
and both state version V.4, 3 Apr 2024. That one comparison establishes that the
archived file is the revision a distributor ships. It does not establish that
the maker has published no newer revision; say so in the provenance row.

Record the snapshot URL as the datasheet link in `design.py`, with the original
URL named in the provenance row.

## 6. Multi-column tables: read the page image

`pdftotext -layout` interleaves the columns of a multi-column table, so a value
can land in the wrong row. In the run the Rubycon YXJ 25 V table was
unreadable as text, and the 25 V rows were read from the page image.

Render the page with `pdftoppm -r 400 -f PAGE -l PAGE -png FILE.pdf OUTPREFIX`
and read the PNG. Rules for numbers read from an image, including the stated
tolerance for scaled dimensions, are in `agents/resource-scout.md`, "When the
primary source is an image".

## 7. What goes in the report

| Item | Content |
|---|---|
| Verified keys | each `lcsc` value, with model, brand, package, stock and read date |
| Omitted keys | each distributor key left out, with the reason (bot check, not read back) |
| Refused endpoints | each endpoint that returned 403 or a bot page, with the URL for a person |
| Datasheet copies | for a dead URL: the snapshot used, and the byte comparison result |
| Inferences | anything resting on a distributor's own parameters, such as a packing suffix not defined on the maker's sheet (`passives-active.md` section 9) |
