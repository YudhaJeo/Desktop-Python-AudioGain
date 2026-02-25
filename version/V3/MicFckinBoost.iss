[Setup]
; GANTI GUID di bawah ini SEKALI saja, lalu biarkan sama untuk semua update versi berikutnya.
; Di Inno Setup: Tools -> Generate GUID -> copy ke AppId di bawah.
AppId={{85DB6A4B-3E7C-401F-9427-6F1EEA7E5E14}}

AppName=MicFckinBoost
AppVersion=1.0.0
AppPublisher=Your Name
AppPublisherURL=https://example.com

; Folder instalasi default (bisa diubah user di wizard)
DefaultDirName={pf}\MicFckinBoost
DefaultGroupName=MicFckinBoost

; Output installer (akan dibuat di folder yang sama dengan file .iss ini)
OutputDir=.
OutputBaseFilename=MicFckinBoost_Setup

; Icon untuk installer & entry di Programs and Features (opsional)
SetupIconFile=D:\Personal App\Audio Gain\assets\app-icon.ico
UninstallDisplayIcon={app}\MicFckinBoost.exe

DisableDirPage=no
DisableProgramGroupPage=no

[Files]
; SALIN semua isi folder build PyInstaller ke direktori instalasi {app}
; Pastikan path Source di bawah ini sesuai dengan hasil dari build_exe.py
Source:"D:\Personal App\Audio Gain\dist\MicFckinBoost\*"; DestDir:"{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
; Shortcut di Start Menu
Name:"{group}\MicFckinBoost"; Filename:"{app}\MicFckinBoost.exe"

; Shortcut di Desktop (opsional — hapus baris ini kalau tidak mau)
Name:"{commondesktop}\MicFckinBoost"; Filename:"{app}\MicFckinBoost.exe"

[Run]
; Jalankan app setelah instal (opsional)
Filename:"{app}\MicFckinBoost.exe"; Description:"Jalankan MicFckinBoost"; Flags: nowait postinstall skipifsilent

