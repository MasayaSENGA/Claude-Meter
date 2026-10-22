@echo off
rem Build with csc.exe bundled in Windows .NET Framework 4.x (no admin / no extra install)
setlocal
set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC%" set CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe
if not exist "%CSC%" (
  echo csc.exe not found.
  exit /b 1
)
if not exist "%~dp0bin" mkdir "%~dp0bin"
"%CSC%" /nologo /target:winexe /optimize+ /codepage:65001 /out:"%~dp0bin\ClaudeMeter.exe" /win32icon:"%~dp0src\app.ico" /r:System.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll /r:System.Web.Extensions.dll "%~dp0src\ClaudeMeter.cs"
if errorlevel 1 exit /b 1
echo Built: %~dp0bin\ClaudeMeter.exe
