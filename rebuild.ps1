param([switch]$SkipDocConversion)
$ErrorActionPreference='Stop'
$pythonPath='C:\Users\Mingc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONIOENCODING='utf-8'
function Run-Python([string]$Script,[string[]]$Extra=@()) {
    & $pythonPath (Join-Path $PSScriptRoot ('scripts/'+$Script)) @Extra
    if ($LASTEXITCODE -ne 0) { throw ('Failed: '+$Script) }
}
Run-Python 'extract_archives.py'
if (!$SkipDocConversion) { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'scripts/convert_doc.ps1') }
Run-Python 'batch_read.py' @('--merge-only')
Run-Python 'prepare_windows_ocr.py'
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'scripts/windows_ocr.ps1') -JobsPath (Join-Path $PSScriptRoot 'cache/windows_ocr_jobs.json')
Run-Python 'batch_read.py' @('--merge-only')
Run-Python 'check_sources.py'
Run-Python 'parse_questions.py'
Run-Python 'verify_answers.py'
Run-Python 'build_semantic.py'
Run-Python 'test_system.py'
Run-Python 'finalize_reports.py'
