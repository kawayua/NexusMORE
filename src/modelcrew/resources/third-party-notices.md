# Third-party notices

## Project license and third-party boundaries

The NexusMORE combined distribution including PyMuPDF is provided under
GNU AGPL version 3 (AGPL-3.0-only); see the root LICENSE and the included
combined-distribution license statement. The prior Apache-2.0 grant for
original NexusMORE work is retained in docs/licenses/Apache-2.0.txt (and in
package licensing resources). This is not an Apache-only combined product.
Third-party works retain their original copyrights, licenses and notices.
Historical reference inventories are not grants for restricted materials.

PyMuPDF 1.27.2.3 is retained. Its official source includes AGPL COPYING and
GPL-3.0-only source headers; MuPDF 1.27.2 includes AGPLv3-or-later notices.
Preserve those per-file terms and the original Artifex notices. No commercial
Artifex license has been obtained or claimed. The combined AGPL distribution
requires corresponding-source and notice obligations to be fulfilled; fetching
a dependency separately through pip does not automatically remove them.
Psycopg LGPL and other bundled-component requirements remain under review.

There is no warranty; see AGPL sections 15 and 16. The source-materials bundle
is prepared separately from the runtime package. Its presence is not a claim
that every third-party obligation or native build mapping has been verified.
Public release remains uncleared. Native executables, model weights, images,
fonts, licensed Word and Docker Desktop retain their own terms. User data and
ordinary generated papers are not automatically subject to the software license.

## Document tools

NexusMORE includes unmodified document-tool resources freshly obtained from
[Anthropic's official skills repository](https://github.com/anthropics/skills)
at commit `2c5958ecac7cee2b583967a2c4981d0f4a75c579`.

The `skills/docx`, `skills/pdf`, and `skills/xlsx` directories in that pinned
snapshot provide the Apache License, Version 2.0. Their license texts are kept
with the imported files:

- [DOCX license](document-tools/upstream/docx/LICENSE.txt)
- [PDF license](document-tools/upstream/pdf/LICENSE.txt)
- [XLSX license](document-tools/upstream/xlsx/LICENSE.txt)

Copyright and other notices embedded in source files are preserved. File URLs,
Git blob hashes, SHA-256 hashes, and version are recorded in
[document-tools/manifest.json](document-tools/manifest.json).
Original file bytes have not been modified. NexusMORE's adapter is separate
from these upstream files. This notice does not assign a license to the rest
of NexusMORE or to other locally available reference materials.

Python libraries listed in requirements remain separately distributed packages
with their own licenses. LibreOffice and PDF rendering utilities are separate
system dependencies; copying Python scripts does not install those programs.
