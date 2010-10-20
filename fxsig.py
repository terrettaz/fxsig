#!/usr/bin/python

__author__ = 'Pierrick Terrettaz'
__date__ = '2010-10-18'
__version__ = '0.2'

import re
import sys
import time
import random
import urllib
import urllib2
import datetime
import optparse

from datetime import datetime, tzinfo, timedelta

class DefaultConverter(object):
    def convert(self, value):
        return value
    
    def __call__(self, dictionary):
        for k, v in dictionary.items():
            dictionary[k] = self.convert(v)
        return dictionary

class DateConverter(DefaultConverter):
    def convert(self, value):
        return datetime.strptime(value, '%b, %d %H:%M %Z')\
            .replace(year=datetime.now().year, tzinfo=DateConverter.gmt)\
            .astimezone(DateConverter.local)\
            .replace(tzinfo=None)
    
    STDOFFSET = timedelta(seconds = -time.timezone)
    if time.daylight:
        DSTOFFSET = timedelta(seconds = -time.altzone)
    else:
        DSTOFFSET = STDOFFSET

    DSTDIFF = DSTOFFSET - STDOFFSET

    class LocalTimezone(tzinfo):
        def utcoffset(self, dt):
            if self._isdst(dt):
                return DateConverter.DSTOFFSET
            else:
                return DateConverter.STDOFFSET
        def dst(self, dt):
            if self._isdst(dt):
                return DateConverter.DSTDIFF
            else:
                return ZERO
        def tzname(self, dt):
            return time.tzname[self._isdst(dt)]
        def _isdst(self, dt):
            tt = (dt.year, dt.month, dt.day,
                  dt.hour, dt.minute, dt.second,
                  dt.weekday(), 0, -1)
            stamp = time.mktime(tt)
            tt = time.localtime(stamp)
            return tt.tm_isdst > 0
            
    class GMT(tzinfo):
        def utcoffset(self,dt):
            return timedelta(0)
        def tzname(self,dt): 
            return "GMT"
        def dst(self,dt):
            return timedelta(0)
    
    gmt = GMT()
    local = LocalTimezone()


class PriceConverter(DefaultConverter):
    def __init__(self, z, padding):
        self.z = z
        self.padding = int(padding)
        
    def convert(self, value):
        result = ''
        for i in range(0,len(value)):
            result += self._convert_char(i, value)
        return float(result)
    
    def _convert_char(self, i, text):
        pos = ord(text[i]) - self.padding - i
        return self.z[pos]

class Foresignal(object):
    def __init__(self, setup):
        self.setup = {'delay':30}
        self.setup.update(setup)
        self.signals = {}
        self.listeners = []
        self.opener = urllib2.build_opener()
        url = 'http://foresignal.com'
        self.request = urllib2.Request(url)
        self.request.add_header('User-Agent', 'Mozilla/5.0 Gecko/20090715 Firefox/3.5.1')
        
        self._init_regx()
    
    def _init_regx(self):
        self.regx_currency_pair = re.compile('<a href="/signals/.+\.php" style="text-decoration:none;">(?P<currency_pair>.+/.+)</a></span>')
        self.regx_action = re.compile('<div class="status"><span class=".+text">(?P<action>.+)</span></div>')
        self.regx_dates = re.compile('</div>From (?P<from>.+)<br>Till (?P<to>.+)<div class="status">')
        self.regx_trend_img = re.compile('<img src="(?P<trend_img>/img/(buy|sell)\.png)">')
        self.regx_buysell_price = re.compile('(Buy|Sell) at <span class=".+text"><font size="\+2"><script type="text/javascript">f\(\'(?P<price>.+)\'\);</script></font></span>')
    
    def load_page(self):
        return self.opener.open(self.request).read()
    
    def process(self):
        content = self.load_page()
        regx_price_decoder_params = re.compile("var z='(?P<z>.+)';function f\(s\)\{var i=0;for \(i=0;i<s.length;i\+\+\)\{document.write\(z.charAt\(s.charCodeAt\(i\)-(?P<padding>\d+)-i\)\);\}\}")
        price_decoder_params = self._get_value(regx_price_decoder_params, content)
        
        lines = filter(lambda line: line.startswith('<div class="symbol'), content.split('\n'))
        params = [price_decoder_params for x in range(len(lines))]
        signals = map(self.parse_signal, lines, params)
        signals = filter(lambda s: s != None, signals)
        signals = sorted(signals, key=lambda signal: signal['from'])
        map(self.process_signal, signals)
    
    def _fire_event(self, event, signal):
        for listener in self.listeners:
            try:
                handler = getattr(listener, 'on_' + event)
                handler(signal)
            except:
                pass
    
    def process_signal(self, signal):
        key = signal['currency_pair']
        action = signal['action']
        current_signal = self.signals[key] if key in self.signals else None
        if not current_signal:
            if action != 'Filled' and action != 'Cancelled':
                self.signals[key] = signal
                self._fire_event('new_signal', signal)
            return
        
        if current_signal != signal:
            if signal['action'] == 'Filled':
                del self.signals[key]
                self._fire_event('finish_signal', signal)
            elif signal['action'] == 'Cancelled':
                del self.signals[key]
                self._fire_event('cancel_signal', signal)
            else:
                self.signals[key] = signal
                self._fire_event('update_signal', signal)
                
    def parse_signal(self, text, price_decoder_params):
        currency_pair = self._get_value(self.regx_currency_pair, text)
        action = self._get_value(self.regx_action, text)
        trend_img = self._get_value(self.regx_trend_img, text)
        dates = self._get_value(self.regx_dates, text, DateConverter())
        buysell_price = self._get_value(self.regx_buysell_price, text, PriceConverter(**price_decoder_params))
        
        if currency_pair:
            signal = {}
            signal.update(currency_pair)
            signal.update(action)
            if trend_img:
                signal.update(trend_img)
                signal.update(buysell_price)
            signal.update(dates)
            return signal
        
    def _get_value(self, regx, text, parser=DefaultConverter()):
        res = regx.search(text)
        if res:
            values = parser(res.groupdict())
            return values
        
    def live(self, base_delay):
        while True:
            self.process()
            delay = base_delay + random.randint(-10, 10) # offuscate regularity
            delay = max(15, delay) # avoid aggressive polling
            time.sleep(int(delay))    
    
    def start(self):
        if self.setup['live_mode']:
            self.live(self.setup['delay'])
        else:
            self.process()
    
    def register(self, listener):
        if listener not in self.listeners:
            self.listeners.append(listener)

class SignalPrinter(object):
    def on_new_signal(self, signal):
        print '-- NEW --'
        print self.desc_signal(signal)
    def on_update_signal(self, signal):
        print '-- UPDATE --'
        print self.desc_signal(signal)
    def on_finish_signal(self, signal):
        print '-- FINISH --'
        print '%(currency_pair)s' % signal
    def on_cancel_signal(self, signal):
        print '-- FINISH --'
        print '%(currency_pair)s' % signal
    def desc_signal(self, signal):
        return '%(currency_pair)s\n%(action)s -> %(price)f\n  from: %(from)s\n  to:   %(to)s' % signal

class SignalNotifier(SignalPrinter):
    def __init__(self):
        if self._init_growl():
            self.ready = True
        elif self._init_pynotify():
            self.ready = True
        else:
            self.ready = False

    def on_new_signal(self, signal):
        self.notify('-- NEW --', self.desc_signal(signal), signal)
    def on_update_signal(self, signal):
        self.notify('-- UPDATE --', self.desc_signal(signal), signal)
    def on_finish_signal(self, signal):
        self.notify('-- FINISH --', '%(currency_pair)s' % signal, signal)
    def on_cancel_signal(self, signal):
        self.notify('-- FINISH --', '%(currency_pair)s' % signal, signal)
    
    def notify(self, title, body, signal):
        notifier = getattr(self, "_notify_%s" % self.system)
        notifier(title, body, signal)

    def _init_growl(self):
        try:
            import Growl
            self.system = 'growl'
            url = urllib2.urlopen('http://foresignal.com/img/buy.png')
            iconbuy = Growl.Image.imageWithData(url.read())
            url = urllib2.urlopen('http://foresignal.com/img/sell.png')
            iconsell = Growl.Image.imageWithData(url.read())
            
            growl_buy = Growl.GrowlNotifier('buy', ['buy'], applicationIcon=iconbuy)
            growl_sell = Growl.GrowlNotifier('sell', ['sell'], applicationIcon=iconsell)
            growl_default = Growl.GrowlNotifier('default', ['default'], applicationIcon=None)
            growl_buy.register()
            growl_sell.register()
            growl_default.register()
            
            self.growl_notifiers = {
                'buy': growl_buy,
                'sell': growl_sell,
                'default': growl_default,
            }
            return True
        except ImportError:
            return False

    def _init_pynotify(self):
        try:
            import pynotify
            self.system = 'pynotify'
            return pynotify.init("Foresignal notifications")
        except ImportError:
            return False

    def _notify_growl(self, title, body, signal):
        notifier = signal['action'].lower()
        if notifier not in self.growl_notifiers:
            notifier = 'default'
        self.growl_notifiers[notifier].notify(notifier, title, body)

    def _notify_pynotify(self, title, body, signal):    
        import pynotify
        n = pynotify.Notification(title, body, 'http://foresignal.com/%(trend_img)s' % signal)
        n.set_urgency(pynotify.URGENCY_LOW)
        n.set_timeout(1000) # 10 seconds
        n.show()

def parse_command_line():
    parser = optparse.OptionParser("usage: %prog [options] [live]")
    parser.add_option('-n', '--disable-notifications', action='store_false', dest='notifications', help='Disable notifications', default=True)
    parser.add_option('-d', '--delay', dest='delay', help='Delay in second to check new signals')
    
    options, args = parser.parse_args()
    
    setup = { 'live_mode': 'live' in args }
    if options.delay:
        setup['delay'] = int(options.delay)
    
    return setup, options

def main():
    try:
        setup, options = parse_command_line()
        foresignal = Foresignal(setup)
        foresignal.register(SignalPrinter())
        if options.notifications:
            foresignal.register(SignalNotifier())
        foresignal.start()
        return 0
    except KeyboardInterrupt:
        return 0

if __name__ == '__main__':
    sys.exit(main())