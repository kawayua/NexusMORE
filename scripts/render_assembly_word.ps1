param([Parameter(Mandatory=$true)][string]$Docx,[Parameter(Mandatory=$true)][string]$Pdf)
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($Docx,$false,$true)
    $document.ExportAsFixedFormat($Pdf,17)
} finally {
    if ($null -ne $document) {
        $document.Close($false)
        [Runtime.InteropServices.Marshal]::ReleaseComObject($document) | Out-Null
    }
    if ($null -ne $word) {
        $word.Quit()
        [Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    }
}
