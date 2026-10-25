param([Parameter(Position=0)][string]$Action='search',[Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
$ErrorActionPreference='Stop'
$pythonPath='C:\Users\Mingc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Bundled Python not found; update pythonPath in run.ps1.' }
$env:PYTHONIOENCODING='utf-8'
$scriptName=switch ($Action) { 'search' {'search_questions.py'} 'exam' {'exam_mode.py'} 'test' {'test_system.py'} default {throw 'Use search, exam or test.'} }
& $pythonPath (Join-Path $PSScriptRoot ('scripts/'+$scriptName)) @Arguments
exit $LASTEXITCODE
