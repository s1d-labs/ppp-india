# parliament: questions and answers on PPP and VGF

This folder holds one script. The script collects Lok Sabha and Rajya Sabha questions on PPP projects and VGF.
It also downloads the answer PDFs. The answers give data that the PPP portal does not show, for example VGF releases per project.

The script needs only Python 3.9 or later. It needs no other packages.

## Sources

| House | List of questions | Answer PDF |
|---|---|---|
| Lok Sabha (13th to 18th) | `sansad.in/api_ls/question/qetFilteredQuestionsAns` | `sansad.in/getFile/...` (16th Lok Sabha and later) |
| Rajya Sabha (all sessions) | `integration.rajyasabha.digital/rsdebate/api/question/search-questions` | `bucketapi.rajyasabha.digital/public-bucket/...` |

- The Lok Sabha search finds the keyword in the subject of the question.
- The Rajya Sabha search finds the exact keyword in the full text.
- Before the 16th Lok Sabha, the list has no PDF link. The script records these questions without a file.
- `eparlib.sansad.in` does not answer from the team box. The script does not use it.

## Use

1. Copy this folder to a computer with Python 3.
2. Run the script:

   ```
   python fetch.py out
   ```

3. Read `out/index.csv`. Open the PDFs in `out/pdf/`.

Options:

- `--kw "text"`: search only for this keyword. You can give `--kw` more than once.
- `--no-pdf`: make the index only. Do not download PDFs.

A second run downloads only the PDFs that are not in `out/pdf/`.

## Output

`out/index.csv` has one row for each question:

| Column | Meaning |
|---|---|
| `house` | `LS` or `RS` |
| `id` | Lok Sabha: `<Lok Sabha>-<S or U><number>-<date>`. Rajya Sabha: the site's question serial number |
| `term` | the Lok Sabha and session, or the Rajya Sabha session |
| `qno`, `qtype`, `date` | question number, starred or unstarred, answer date (DD.MM.YYYY) |
| `ministry`, `subject` | the ministry that answered, and the subject of the question |
| `keywords` | the keywords that found the question |
| `url`, `file`, `bytes`, `sha256` | the source of the PDF, the local file, its size and its checksum |

The index does not include the names of members.

## Speed

The script sends one request every 2 seconds. When a request fails, it waits and tries again three times.
Do not make the delay shorter.
