$ErrorActionPreference = 'Stop'
$rootDir = Split-Path $PSScriptRoot -Parent
$sources = Get-Content -LiteralPath (Join-Path $rootDir 'database/source_index.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.AutomationSecurity = 3
$word.Options.SaveNormalPrompt = $false
$results = @()
try {
  foreach ($source in $sources.files) {
    if ($source.type -ne '.doc') { continue }
    $textPath = Join-Path $rootDir ('cache/' + $source.source_id + '.word.txt')
    $docxPath = Join-Path $rootDir ('cache/' + $source.source_id + '.docx')
    if (Test-Path -LiteralPath $textPath) { continue }
    $doc = $null
    try {
      $doc = $word.Documents.Open($source.path, $false, $true, $false)
      try { $doc.Content.ListFormat.ConvertNumbersToText() } catch { }
      $text = $doc.Content.Text
      [System.IO.File]::WriteAllText($textPath, $text, [System.Text.Encoding]::UTF8)
      $results += @{source_id=$source.source_id;status='converted';characters=$text.Length;paragraphs=$doc.Paragraphs.Count;inline_shapes=$doc.InlineShapes.Count;shapes=$doc.Shapes.Count}
      Write-Output ($source.source_id + ' ' + $text.Length + ' chars')
    } catch {
      $results += @{source_id=$source.source_id;status='failed';error=$_.Exception.Message}
      Write-Output ($source.source_id + ' FAILED ' + $_.Exception.Message)
    } finally { if ($null -ne $doc) { $doc.Close(0); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) } }
    $results | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $rootDir 'cache/doc_conversion.json') -Encoding UTF8
  }
} finally { $word.Quit(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) }
