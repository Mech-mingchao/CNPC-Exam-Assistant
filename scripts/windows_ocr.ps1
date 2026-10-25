param([string]$JobsPath,[string]$ImagesDirectory,[switch]$Overwrite)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime] | Out-Null
$taskMethod=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await-Result($Operation,[Type]$ResultType) {
    $task=$taskMethod.MakeGenericMethod($ResultType).Invoke($null,@($Operation))
    $task.GetAwaiter().GetResult()
}
$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language('zh-Hans-CN')))
if ($null -eq $engine) { throw 'Chinese Windows OCR engine unavailable.' }
if ($ImagesDirectory) {
    $jobs=@(Get-ChildItem -LiteralPath $ImagesDirectory -File | ForEach-Object { @{image=$_.FullName;output=(Join-Path (Split-Path $ImagesDirectory -Parent) ('ocr/'+$_.BaseName+'.json'))} })
} else { $jobs=Get-Content -LiteralPath $JobsPath -Raw -Encoding UTF8 | ConvertFrom-Json }
$done=0
foreach ($job in $jobs) {
    if ((Test-Path -LiteralPath $job.output) -and !$Overwrite) { continue }
    try {
        $file=Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($job.image)) ([Windows.Storage.StorageFile])
        $stream=Await-Result ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        try {
            $decoder=Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bitmap=Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            try { $result=Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult]) } finally { $bitmap.Dispose() }
        } finally { $stream.Dispose() }
        $boxes=@($result.Lines | ForEach-Object {
            $words=@($_.Words)
            $minX=($words | ForEach-Object {$_.BoundingRect.X} | Measure-Object -Minimum).Minimum
            $minY=($words | ForEach-Object {$_.BoundingRect.Y} | Measure-Object -Minimum).Minimum
            $maxX=($words | ForEach-Object {$_.BoundingRect.X+$_.BoundingRect.Width} | Measure-Object -Maximum).Maximum
            $maxY=($words | ForEach-Object {$_.BoundingRect.Y+$_.BoundingRect.Height} | Measure-Object -Maximum).Maximum
            @{text=$_.Text;confidence=$null;box=@($minX,$minY,$maxX,$maxY);y=$minY;x=$minX}
        } | Sort-Object @{Expression={[math]::Round($_.y/12)}},@{Expression={$_.x}})
        $lines=@($boxes | ForEach-Object {$_.text})
        $data=@{text=($lines -join "`n");ocr_boxes=$boxes;method='ocr_windows';requires_visual_review=$true;ocr_language='zh-Hans-CN';reading_order='row_then_x_v2'}
        $json=$data | ConvertTo-Json -Depth 8 -Compress
        [System.IO.File]::WriteAllText($job.output,$json,(New-Object System.Text.UTF8Encoding($false)))
        $done++
        if ($done % 20 -eq 0) { Write-Output ('Windows OCR '+$done+'/'+$jobs.Count) }
        Remove-Item -LiteralPath $job.image
    } catch { if (!(Test-Path -LiteralPath $job.output)) { Write-Output ('OCR FAILED '+$job.image+' '+$_.Exception.Message) } }
}
Write-Output ('Windows OCR completed '+$done)
