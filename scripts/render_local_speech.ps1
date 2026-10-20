param([Parameter(Mandatory=$true)][string]$TextPath, [Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speech = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $text = [System.IO.File]::ReadAllText($TextPath, [System.Text.Encoding]::UTF8)
    $voice = $speech.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh-*' } | Select-Object -First 1
    if ($text -match '[\p{IsCJKUnifiedIdeographs}]' -and -not $voice) { throw 'LOCAL_CHINESE_VOICE_UNAVAILABLE' }
    if ($voice) { $speech.SelectVoice($voice.VoiceInfo.Name) }
    $speech.SetOutputToWaveFile($OutputPath)
    $speech.Speak($text)
} finally { $speech.Dispose() }
