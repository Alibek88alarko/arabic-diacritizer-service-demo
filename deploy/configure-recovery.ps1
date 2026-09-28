# Auto-start on boot and restart on failure for the pywin32 service. Run as Administrator after `install`.
param([string]$Name = "DiacritizerAPI")
sc.exe config $Name start= auto
# restart 5 s after the 1st, 2nd and any later failure; reset the failure counter after a day
sc.exe failure $Name reset= 86400 actions= restart/5000/restart/5000/restart/5000
sc.exe failureflag $Name 1
sc.exe qfailure $Name
