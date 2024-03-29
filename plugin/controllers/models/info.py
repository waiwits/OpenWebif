# -*- coding: utf-8 -*-

##############################################################################
#                        2011-2017 E2OpenPlugins                             #
#                                                                            #
#  This file is open source software; you can redistribute it and/or modify  #
#     it under the terms of the GNU General Public License version 2 as      #
#               published by the Free Software Foundation.                   #
#                                                                            #
##############################################################################

import os
import sys
import time
from twisted.web import version
from socket import has_ipv6, AF_INET6, AF_INET, inet_ntop, inet_pton, getaddrinfo

import NavigationInstance
from Components.About import about
from Components.config import config
from Components.NimManager import nimmanager
from Components.Harddisk import harddiskmanager
from Components.Network import iNetwork
from ServiceReference import ServiceReference
from RecordTimer import parseEvent
from timer import TimerEntry
from Screens.InfoBar import InfoBar
from Tools.Directories import fileExists, pathExists
from enigma import eDVBVolumecontrol, eServiceCenter, eServiceReference, getEnigmaVersionString, eEPGCache, getBoxType, getBoxBrand
from Tools.StbHardware import getFPVersion, getBoxProc
from ..i18n import _
from ..defaults import OPENWEBIFVER, TRANSCODING
from boxbranding import getImageDistro, getImageVersion, getImageBuild, getOEVersion
from owibranding import getLcd, getGrabPip


def getEnigmaVersionString():
	return about.getEnigmaVersionString()

STATICBOXINFO = None

def getFriendlyImageDistro():
	dist = getImageDistro().replace("openvision", "Open Vision")
	return dist

def getIPMethod(iface):
	# iNetwork.getAdapterAttribute is crap and not portable
	ipmethod = _("SLAAC")
	if fileExists('/etc/network/interfaces'):
		ifaces = '/etc/network/interfaces'
		for line in file(ifaces).readlines():
			if not line.startswith('#'):
				if line.startswith('iface') and "inet6" in line and iface in line:
					if "static" in line:
						ipmethod = _("static")
					if "dhcp" in line:
						ipmethod = _("DHCP")
					if "manual" in line:
						ipmethod = _("manual/disabled")
					if "6to4" in line:
						ipmethod = "6to4"
	return ipmethod


def getIPv4Method(iface):
	# iNetwork.getAdapterAttribute is crap and not portable
	ipv4method = _("static")
	if fileExists('/etc/network/interfaces'):
		ifaces = '/etc/network/interfaces'
		for line in file(ifaces).readlines():
			if not line.startswith('#'):
				if line.startswith('iface') and "inet " in line and iface in line:
					if "static" in line:
						ipv4method = _("static")
					if "dhcp" in line:
						ipv4method = _("DHCP")
					if "manual" in line:
						ipv4method = _("manual/disabled")
	return ipv4method


def getLinkSpeed(iface):
	try:
		with open('/sys/class/net/' + iface + '/speed', 'r') as f:
			speed = f.read().strip()
	except:  # noqa: E722
		speed = _("unknown")
	speed = str(speed) + " MBit/s"
	speed = speed.replace("10000 MBit/s", "10 GBit/s")
	speed = speed.replace("1000 MBit/s", "1 GBit/s")
	return speed


def getNICChipSet(iface):
	nic = _("unknown")
	try:
		nic = os.path.realpath('/sys/class/net/' + iface + '/device/driver').split('/')[-1]
		nic = str(nic)
	except:  # noqa: E722
		pass
	return nic


def getFriendlyNICChipSet(iface):
	friendlynic = getNICChipSet(iface)
	friendlynic = friendlynic.replace("bcmgenet", "Broadcom Gigabit Ethernet")
	friendlynic = friendlynic.replace("bcmemac", "Broadcom STB 10/100 EMAC")
	return friendlynic


def normalize_ipv6(orig):
	net = []

	if '/' in orig:
		net = orig.split('/')
		if net[1] == "128":
			del net[1]
	else:
		net.append(orig)

	addr = net[0]

	addr = inet_ntop(AF_INET6, inet_pton(AF_INET6, addr))

	if len(net) == 2:
		addr += "/" + net[1]

	return (addr)


def getAdapterIPv6(ifname):
	addr = _("IPv4-only kernel")
	firstpublic = None

	if fileExists('/proc/net/if_inet6'):
		addr = _("IPv4-only Python/Twisted")

		if has_ipv6 and version.major >= 12:
			proc = '/proc/net/if_inet6'
			tempaddrs = []
			for line in file(proc).readlines():
				if line.startswith('fe80'):
					continue

				tmpaddr = ""
				tmp = line.split()
				if ifname == tmp[5]:
					tmpaddr = ":".join([tmp[0][i:i + 4] for i in range(0, len(tmp[0]), 4)])

					if firstpublic is None and (tmpaddr.startswith('2') or tmpaddr.startswith('3')):
						firstpublic = normalize_ipv6(tmpaddr)

					if tmp[2].lower() != "ff":
						tmpaddr = "%s/%s" % (tmpaddr, int(tmp[2].lower(), 16))

					tmpaddr = normalize_ipv6(tmpaddr)
					tempaddrs.append(tmpaddr)

			if len(tempaddrs) > 1:
				tempaddrs.sort()
				addr = ', '.join(tempaddrs)
			elif len(tempaddrs) == 1:
				addr = tempaddrs[0]
			elif len(tempaddrs) == 0:
				addr = _("none/IPv4-only network")

	return {'addr': addr, 'firstpublic': firstpublic}


def formatIp(ip):
	if ip is None or len(ip) != 4:
		return "0.0.0.0"  # nosec
	return "%d.%d.%d.%d" % (ip[0], ip[1], ip[2], ip[3])


def getInfo(session=None, need_fullinfo=False):
	# TODO: get webif versione somewhere!
	info = {}
	global STATICBOXINFO

	if not (STATICBOXINFO is None or need_fullinfo):
		return STATICBOXINFO

	info['brand'] = getBoxBrand()
	info['model'] = getBoxType()
	info['boxtype'] = getBoxType()
	info['machinebuild'] = getBoxProc()

	try:
		info['lcd'] = getLcd()
	except: # temporary due OE-A
		info['lcd'] = 0

	try:
		info['grabpip'] = getGrabPip()
	except: # temporary due OE-A
		info['grabpip'] = 0

	cpu = about.getCPUInfoString()
	info['chipset'] = cpu
	info['cpubrand'] = about.getCPUBrand()
	info['cpuarch'] = about.getCPUArch()
	info['flashtype'] = about.getFlashType()

	memFree = 0
	for line in open("/proc/meminfo", 'r'):
		parts = line.split(':')
		key = parts[0].strip()
		if key == "MemTotal":
			info['mem1'] = parts[1].strip().replace("kB", _("kB"))
		elif key in ("MemFree", "Buffers", "Cached"):
			memFree += int(parts[1].strip().split(' ', 1)[0])
	info['mem2'] = "%s %s" % (memFree, _("kB"))
	info['mem3'] = _("%s free / %s total") % (info['mem2'], info['mem1'])

	try:
		f = open("/proc/uptime", "rb")
		uptime = int(float(f.readline().split(' ', 2)[0].strip()))
		f.close()
		uptimetext = ''
		if uptime > 86400:
			d = uptime / 86400
			uptime = uptime % 86400
			uptimetext += '%dd ' % d
		uptimetext += "%d:%.2d" % (uptime / 3600, (uptime % 3600) / 60)
	except:  # noqa: E722
		uptimetext = "?"

	info['uptime'] = uptimetext

	info["webifver"] = OPENWEBIFVER
	info['imagedistro'] = getImageDistro()
	info['friendlyimagedistro'] = getFriendlyImageDistro()
	info['oever'] = getOEVersion()
	info['visionversion'] = about.getVisionVersion()
	info['visionrevision'] = about.getVisionRevision()
	info['visionmodule'] = about.getVisionModule()
	info['imagever'] = getImageVersion()

	ib = getImageBuild()
	if ib:
		info['imagever'] = info['imagever'] + "." + ib

	info['enigmaver'] = getEnigmaVersionString()
	info['driverdate'] = about.getDriverInstalledDate()
	info['kernelver'] = about.getKernelVersionString()
	info['dvbapitype'] = about.getDVBAPI()
	info['gstreamerversion'] = about.getGStreamerVersionString(cpu)
	info['ffmpegversion'] = about.getFFmpegVersionString()
	info['pythonversion'] = about.getPythonVersionString()

	try:
		info['fp_version'] = getFPVersion()
	except:  # noqa: E722
		info['fp_version'] = None

	friendlychipsetdescription = _("Chipset")
	friendlychipsettext = info['chipset']
	if not (info['fp_version'] is None or info['fp_version'] == 0):
		friendlychipsetdescription = friendlychipsetdescription + " (" + _("Frontprocessor Version") + ")"
		friendlychipsettext = friendlychipsettext + " (" + str(info['fp_version']) + ")"

	info['friendlychipsetdescription'] = friendlychipsetdescription
	info['friendlychipsettext'] = friendlychipsettext
	info['tuners'] = []
	for i in range(0, nimmanager.getSlotCount()):
		print "[OpenWebif] -D- tuner '%d' '%s' '%s'" % (i, nimmanager.getNimName(i), nimmanager.getNim(i).getSlotName())
		info['tuners'].append({
			"name": nimmanager.getNim(i).getSlotName(),
			"type": nimmanager.getNimName(i) + " (" + nimmanager.getNim(i).getFriendlyType() + ")",
			"rec": "",
			"live": ""
		})

	info['ifaces'] = []
	ifaces = iNetwork.getConfiguredAdapters()
	for iface in ifaces:
		info['ifaces'].append({
			"name": iNetwork.getAdapterName(iface),
			"friendlynic": getFriendlyNICChipSet(iface),
			"linkspeed": getLinkSpeed(iface),
			"mac": iNetwork.getAdapterAttribute(iface, "mac"),
			"dhcp": iNetwork.getAdapterAttribute(iface, "dhcp"),
			"ipv4method": getIPv4Method(iface),
			"ip": formatIp(iNetwork.getAdapterAttribute(iface, "ip")),
			"mask": formatIp(iNetwork.getAdapterAttribute(iface, "netmask")),
			"v4prefix": sum([bin(int(x)).count('1') for x in formatIp(iNetwork.getAdapterAttribute(iface, "netmask")).split('.')]),
			"gw": formatIp(iNetwork.getAdapterAttribute(iface, "gateway")),
			"ipv6": getAdapterIPv6(iface)['addr'],
			"ipmethod": getIPMethod(iface),
			"firstpublic": getAdapterIPv6(iface)['firstpublic']
		})

	info['hdd'] = []
	for hdd in harddiskmanager.hdd:
		dev = hdd.findMount()
		if dev:
			stat = os.statvfs(dev)
			free = stat.f_bavail * stat.f_frsize / 1048576.
		else:
			free = -1

		if free <= 1024:
			free = "%i %s" % (free, _("MB"))
		else:
			free = free / 1024.
			free = "%.1f %s" % (free, _("GB"))

		size = hdd.diskSize() * 1000000 / 1048576.
		if size > 1048576:
			size = "%.1f %s" % ((size / 1048576.), _("TB"))
		elif size > 1024:
			size = "%.1f %s" % ((size / 1024.), _("GB"))
		else:
			size = "%d %s" % (size, _("MB"))

		iecsize = hdd.diskSize()
		# Harddisks > 1000 decimal Gigabytes are labelled in TB
		if iecsize > 1000000:
			iecsize = (iecsize + 50000) // float(100000) / 10
			# Omit decimal fraction if it is 0
			if (iecsize % 1 > 0):
				iecsize = "%.1f %s" % (iecsize, _("TB"))
			else:
				iecsize = "%d %s" % (iecsize, _("TB"))
		# Round harddisk sizes beyond ~300GB to full tens: 320, 500, 640, 750GB
		elif iecsize > 300000:
			iecsize = "%d %s" % (((iecsize + 5000) // 10000 * 10), _("GB"))
		# ... be more precise for media < ~300GB (Sticks, SSDs, CF, MMC, ...): 1, 2, 4, 8, 16 ... 256GB
		elif iecsize > 1000:
			iecsize = "%d %s" % (((iecsize + 500) // 1000), _("GB"))
		else:
			iecsize = "%d %s" % (iecsize, _("MB"))

		info['hdd'].append({
			"model": hdd.model(),
			"capacity": size,
			"labelled_capacity": iecsize,
			"free": free,
			"mount": dev,
			"friendlycapacity": _("%s free / %s total") % (free, size + ' ("' + iecsize + '")')
		})

	info['shares'] = []
	autofiles = ('/etc/auto.network', '/etc/auto.network_vti')
	for autofs in autofiles:
		if fileExists(autofs):
			method = "autofs"
			for line in file(autofs).readlines():
				if not line.startswith('#'):
					# Replace escaped spaces that can appear inside credentials with underscores
					# Not elegant but we wouldn't want to expose credentials on the OWIF anyways
					tmpline = line.replace("\ ", "_")
					tmp = tmpline.split()
					if not len(tmp) == 3:
						continue
					name = tmp[0].strip()
					type = "unknown"
					if "cifs" in tmp[1]:
						# Linux still defaults to SMBv1
						type = "SMBv1.0"
						settings = tmp[1].split(",")
						for setting in settings:
							if setting.startswith("vers="):
								type = setting.replace("vers=", "SMBv")
					elif "nfs" in tmp[1]:
						type = "NFS"

					# Default is r/w
					mode = _("r/w")
					settings = tmp[1].split(",")
					for setting in settings:
						if setting == "ro":
							mode = _("r/o")

					uri = tmp[2]
					parts = []
					parts = tmp[2].split(':')
					if parts[0] is "":
						server = uri.split('/')[2]
						uri = uri.strip()[1:]
					else:
						server = parts[0]

					ipaddress = None
					if server:
						# Will fail on literal IPs
						try:
							# Try IPv6 first, as will Linux
							if has_ipv6:
								tmpaddress = None
								tmpaddress = getaddrinfo(server, 0, AF_INET6)
								if tmpaddress:
									ipaddress = "[" + list(tmpaddress)[0][4][0] + "]"
							# Use IPv4 if IPv6 fails or is not present
							if ipaddress is None:
								tmpaddress = None
								tmpaddress = getaddrinfo(server, 0, AF_INET)
								if tmpaddress:
									ipaddress = list(tmpaddress)[0][4][0]
						except:  # noqa: E722
							pass

					friendlyaddress = server
					if ipaddress is not None and not ipaddress == server:
						friendlyaddress = server + " (" + ipaddress + ")"
					info['shares'].append({
						"name": name,
						"method": method,
						"type": type,
						"mode": mode,
						"path": uri,
						"host": server,
						"ipaddress": ipaddress,
						"friendlyaddress": friendlyaddress
					})
	# TODO: fstab

	info['transcoding'] = TRANSCODING

	info['EX'] = ''

	if session:
		try:
# gets all current stream clients for images using eStreamServer
# TODO: merge eStreamServer and streamList
# TODO: get tuner info for streams
# TODO: get recoding/timer info if more than one

			info['streams'] = []
			try:
				streams = []
				from enigma import eStreamServer
				streamServer = eStreamServer.getInstance()
				if streamServer is not None:
					for x in streamServer.getConnectedClients():
						servicename = ServiceReference(x[1]).getServiceName() or "(unknown service)"
						if int(x[2]) == 0:
							strtype = "S"
						else:
							strtype = "T"
						info['streams'].append({
							"ref": x[1],
							"name": servicename,
							"ip": x[0],
							"type": strtype
						})
			except Exception, error:
				print "[OpenWebif] -D- no eStreamServer %s" % error
			
			recs = NavigationInstance.instance.getRecordings()
			if recs:
# only one stream and only TV
				from Plugins.Extensions.OpenWebif.controllers.stream import streamList
				s_name = ''
				# s_cip = ''

				print "[OpenWebif] -D- streamList count '%d'" % len(streamList)
				if len(streamList) == 1:
					from Screens.ChannelSelection import service_types_tv
					# from enigma import eEPGCache
					# epgcache = eEPGCache.getInstance()
					serviceHandler = eServiceCenter.getInstance()
					services = serviceHandler.list(eServiceReference('%s ORDER BY name' % (service_types_tv)))
					channels = services and services.getContent("SN", True)
					s = streamList[0]
					srefs = s.ref.toString()
					for channel in channels:
						if srefs == channel[0]:
							s_name = channel[1] + ' (' + s.clientIP + ')'
							break
				print "[OpenWebif] -D- s_name '%s'" % s_name

# only for debug
				for stream in streamList:
					srefs = stream.ref.toString()
					print "[OpenWebif] -D- srefs '%s'" % srefs

				sname = ''
				timers = []
				for timer in NavigationInstance.instance.RecordTimer.timer_list:
					if timer.isRunning() and not timer.justplay:
						timers.append(timer.service_ref.getServiceName().replace('\xc2\x86', '').replace('\xc2\x87', ''))
						print "[OpenWebif] -D- timer '%s'" % timer.service_ref.getServiceName()
# TODO: more than one recording
				if len(timers) == 1:
					sname = timers[0]

				if sname == '' and s_name != '':
					sname = s_name

				print "[OpenWebif] -D- recs count '%d'" % len(recs)

				for rec in recs:
					feinfo = rec.frontendInfo()
					frontendData = feinfo and feinfo.getAll(True)
					if frontendData is not None:
						cur_info = feinfo.getTransponderData(True)
						if cur_info:
							nr = frontendData['tuner_number']
							info['tuners'][nr]['rec'] = getOrbitalText(cur_info) + ' / ' + sname

			service = session.nav.getCurrentService()
			if service is not None:
				sname = service.info().getName()
				feinfo = service.frontendInfo()
				frontendData = feinfo and feinfo.getAll(True)
				if frontendData is not None:
					cur_info = feinfo.getTransponderData(True)
					if cur_info:
						nr = frontendData['tuner_number']
						info['tuners'][nr]['live'] = getOrbitalText(cur_info) + ' / ' + sname
		except Exception, error:
			info['EX'] = error

	STATICBOXINFO = info
	return info


def getOrbitalText(cur_info):
	if cur_info:
		tunerType = cur_info.get('tuner_type')
		if tunerType == "DVB-S":
			pos = int(cur_info.get('orbital_position'))
			return getOrb(pos)
		if cur_info.get("system", -1) == 1:
			tunerType += "2"
		return tunerType
	return ''

def getOrb(pos):
	direction = _("E")
	if pos > 1800:
		pos = 3600 - pos
		direction = _("W")
	return "%d.%d° %s" % (pos / 10, pos % 10, direction)


def getFrontendStatus(session):
	inf = {}
	inf['tunertype'] = ""
	inf['tunernumber'] = ""
	inf['snr'] = ""
	inf['snr_db'] = ""
	inf['agc'] = ""
	inf['ber'] = ""

	service = session.nav.getCurrentService()
	if service is None:
		return inf
	feinfo = service.frontendInfo()
	frontendData = feinfo and feinfo.getAll(True)

	if frontendData is not None:
		inf['tunertype'] = frontendData.get("tuner_type", "UNKNOWN")
		inf['tunernumber'] = frontendData.get("tuner_number")

	frontendStatus = feinfo and feinfo.getFrontendStatus()
	if frontendStatus is not None:
		percent = frontendStatus.get("tuner_signal_quality")
		if percent is not None:
			inf['snr'] = int(percent * 100 / 65535)
			inf['snr_db'] = inf['snr']
		percent = frontendStatus.get("tuner_signal_quality_db")
		if percent is not None:
			inf['snr_db'] = "%3.02f" % (percent / 100.0)
		percent = frontendStatus.get("tuner_signal_power")
		if percent is not None:
			inf['agc'] = int(percent * 100 / 65535)
		percent = frontendStatus.get("tuner_bit_error_rate")
		if percent is not None:
			inf['ber'] = int(percent * 100 / 65535)

	return inf


def getCurrentTime():
	t = time.localtime()
	return {
		"status": True,
		"time": "%2d:%02d:%02d" % (t.tm_hour, t.tm_min, t.tm_sec)
	}


def getStreamServiceName(ref):
	if isinstance(ref, eServiceReference):
		servicereference = ServiceReference(ref)
		if servicereference:
			return servicereference.getServiceName().replace('\xc2\x86', '').replace('\xc2\x87', '')
	return ""


def getStreamEventName(ref):
	if isinstance(ref, eServiceReference):
		epg = eEPGCache.getInstance()
		event = epg and epg.lookupEventTime(ref, -1, 0)
		if event:
			return event.getEventName()
	return ""


def getStatusInfo(self):
	# Get Current Volume and Mute Status
	vcontrol = eDVBVolumecontrol.getInstance()
	statusinfo = {
		'volume': vcontrol.getVolume(),
		'muted': vcontrol.isMuted(),
		'transcoding': TRANSCODING,
		'currservice_filename': "",
		'currservice_id': -1,
	}

	# Get currently running Service
	event = None
	serviceref = self.session.nav.getCurrentlyPlayingServiceReference()
	serviceref_string = None
	currservice_station = None
	if serviceref is not None:
		serviceHandler = eServiceCenter.getInstance()
		serviceHandlerInfo = serviceHandler.info(serviceref)

		service = self.session.nav.getCurrentService()
		serviceinfo = service and service.info()
		event = serviceinfo and serviceinfo.getEvent(0)
		serviceref_string = serviceref.toString()
		currservice_station = serviceHandlerInfo.getName(
			serviceref).replace('\xc2\x86', '').replace('\xc2\x87', '')
	else:
		event = None
		serviceHandlerInfo = None

	if event is not None:
		# (begin, end, name, description, eit)
		curEvent = parseEvent(event)
		begin_timestamp = int(curEvent[0]) + (config.recording.margin_before.value * 60)
		end_timestamp = int(curEvent[1]) - (config.recording.margin_after.value * 60)
		statusinfo['currservice_name'] = curEvent[2].replace('\xc2\x86', '').replace('\xc2\x87', '')
		statusinfo['currservice_serviceref'] = serviceref_string
		statusinfo['currservice_begin'] = time.strftime("%H:%M", (time.localtime(begin_timestamp)))
		statusinfo['currservice_begin_timestamp'] = begin_timestamp
		statusinfo['currservice_end'] = time.strftime("%H:%M", (time.localtime(end_timestamp)))
		statusinfo['currservice_end_timestamp'] = end_timestamp
		statusinfo['currservice_description'] = curEvent[3]
		if len(curEvent[3].decode('utf-8')) > 220:
			statusinfo['currservice_description'] = curEvent[3].decode('utf-8')[0:220].encode('utf-8') + "..."
		statusinfo['currservice_station'] = currservice_station
		if statusinfo['currservice_serviceref'].startswith('1:0:0'):
			statusinfo['currservice_filename'] = '/' + '/'.join(serviceref_string.split("/")[1:])
		full_desc = statusinfo['currservice_name'] + '\n'
		full_desc += statusinfo['currservice_begin'] + " - " + statusinfo['currservice_end'] + '\n\n'
		full_desc += event.getExtendedDescription().replace('\xc2\x86', '').replace('\xc2\x87', '').replace('\xc2\x8a', '\n')
		statusinfo['currservice_fulldescription'] = full_desc
		statusinfo['currservice_id'] = curEvent[4]
	else:
		statusinfo['currservice_name'] = "N/A"
		statusinfo['currservice_begin'] = ""
		statusinfo['currservice_end'] = ""
		statusinfo['currservice_description'] = ""
		statusinfo['currservice_fulldescription'] = "N/A"
		if serviceref:
			statusinfo['currservice_serviceref'] = serviceref_string
			if statusinfo['currservice_serviceref'].startswith('1:0:0') or statusinfo['currservice_serviceref'].startswith('4097:0:0'):
				this_path = '/' + '/'.join(serviceref_string.split("/")[1:])
				if os.path.exists(this_path):
					statusinfo['currservice_filename'] = this_path
			if serviceHandlerInfo:
				statusinfo['currservice_station'] = currservice_station
			elif serviceref_string.find("http") != -1:
				statusinfo['currservice_station'] = serviceref_string.replace('%3a', ':')[serviceref_string.find("http"):]
			else:
				statusinfo['currservice_station'] = "N/A"

	# Get Standby State
	from Screens.Standby import inStandby
	if inStandby is None:
		statusinfo['inStandby'] = "false"
	else:
		statusinfo['inStandby'] = "true"

	# Get recording state
	recs = NavigationInstance.instance.getRecordings()
	if recs:
		statusinfo['isRecording'] = "true"
		statusinfo['Recording_list'] = "\n"
		for timer in NavigationInstance.instance.RecordTimer.timer_list:
			if timer.state == TimerEntry.StateRunning:
				if not timer.justplay:
					statusinfo['Recording_list'] += timer.service_ref.getServiceName().replace('\xc2\x86', '').replace('\xc2\x87', '') + ": " + timer.name + "\n"
		if statusinfo['Recording_list'] == "\n":
			statusinfo['isRecording'] = "false"
	else:
		statusinfo['isRecording'] = "false"

	return statusinfo


def getAlternativeChannels(service):
	alternativeServices = eServiceCenter.getInstance().list(eServiceReference(service))
	return alternativeServices and alternativeServices.getContent("S", True)


def GetWithAlternative(service, onlyFirst=True):
	if service.startswith('1:134:'):
		channels = getAlternativeChannels(service)
		if channels:
			if onlyFirst:
				return channels[0]
			else:
				return channels
	if onlyFirst:
		return service
	else:
		return None

def getPipStatus():
	return int(getInfo()['grabpip'] and hasattr(InfoBar.instance, 'session') and InfoBar.instance.session.pipshown)

def testPipStatus(self):
	pipinfo = {
		'pip': getPipStatus(),
	}
	return pipinfo
