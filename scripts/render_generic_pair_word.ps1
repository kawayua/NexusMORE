$ErrorActionPreference='Stop'
$docxPath=(Resolve-Path -LiteralPath 'output/paper/generic-q1-q2-20261110-v7/paper.docx').Path
$qaPath=Join-Path (Get-Location) 'output/paper/generic-q1-q2-20261110-v7/qa'
[System.IO.Directory]::CreateDirectory($qaPath) | Out-Null
$pdfPath=Join-Path $qaPath 'word-render.pdf'
$word=$null
$doc=$null
try {
    $word=New-Object -ComObject Word.Application
    $word.Visible=$false
    $word.DisplayAlerts=0
    $word.AutomationSecurity=3
    $doc=$word.Documents.Open($docxPath,$false,$true)
    $doc.ExportAsFixedFormat($pdfPath,17)
    Write-Output "Word native rendering completed"
} finally {
    if ($null -ne $doc) { $doc.Close($false);[Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null }
    if ($null -ne $word) { $word.Quit();[Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null }
}
