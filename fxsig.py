#!/usr/bin/python

__author__ = 'Pierrick Terrettaz'
__date__ = '2010-10-18'
__version__ = '0.2'

import os
import re
import sys
import time
import random
import urllib
import urllib2
import datetime
import optparse
import threading

from datetime import datetime, tzinfo, timedelta

class DefaultConverter(object):
    def convert(self, value):
        return value
    def _check_value(self, value):
        if type(value) != str: raise TypeError('Value not a string')
        if value.strip() == '': raise ValueError('Value is blank')

class DateConverter(DefaultConverter):
    def convert(self, value):
        if not value: return None
        self._check_value(value)
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
    def set_params(self, z, padding):
        self.z = z
        self.padding = int(padding)
        
    def convert(self, value):
        if not value: return None
        self._check_params()
        self._check_value(value)
        result = ''
        for i in range(0,len(value)):
            result += self._convert_char(i, value)
        return float(result)
    
    def _check_params(self):
        if not self.z or not self.padding:
            raise AttributeError('parameters are not set correctly')
    
    def _convert_char(self, i, text):
        pos = ord(text[i]) - self.padding - i
        return self.z[pos]


class HTMLScraper(object):
    def __init__(self, url):
        self.opener = urllib2.build_opener()
        self.request = urllib2.Request(url)
        self.request.add_header('User-Agent', 'Mozilla/5.0 Gecko/20090715 Firefox/3.5.1')
        self.regx = []
        self.converters = {}
        self.line_validators = []
    
    def _load_page(self):
        return self.opener.open(self.request).read()
    
    def get_value(self, regx, text):
        res = regx.search(text)
        if res:
            values = res.groupdict()
            for k, v in values.items():
                if k in self.converters:
                    values[k] = self.converters[k].convert(v)
                    
            return values
    
    def _parse_line(self, line):
        values = {}
        for regx in self.regx:
            value = self.get_value(regx, line)
            if value:
                values.update(self.get_value(regx, line))
        return values

    def fetch(self):
        self.content = self._load_page()
        return self.content
        
    def get_values(self):
        assert self.content, 'Content is not yet loaded, call method "fetch" before'
        
        lines = self.content.split('\n')
        for validator in self.line_validators:
            lines = filter(validator, lines)
        values = map(self._parse_line, lines)
        values = filter(lambda value: value != None, values)
        return values
        
class PriceProvider(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.scraper = HTMLScraper('http://www.fxstreet.com/rates-charts/forex-rates/')
        self.scraper.line_validators.append(lambda line: '<td class="col-name">' in line)
        self.scraper.regx.append(re.compile('<td class="col-name">(?P<currency_pair>.+/.+)</td><td id="last_.+">(?P<mid>.+)</td><td id="open_.+">'))
        self.prices = {}
        self.update_prices()
        self.start()
    
    def stop(self):
        self._Thread__stop()
    
    def get_price(self, currency_pair):
        return self.prices[currency_pair] if currency_pair in self.prices else None
    
    def update_prices(self):
        try:
            prices = {}
            self.scraper.fetch()
            for price in self.scraper.get_values():
                prices[price['currency_pair']] = price
            
            self.prices.update(prices)
        except urllib2.URLError, e:
            pass # prices cannot be loaded
            
    def run(self):
        while True:
            time.sleep(10)
            self.update_prices()
        
class Foresignal(object):
    def __init__(self, setup):
        self.setup = {'delay':30}
        self.setup.update(setup)
        self.signals = {}
        self.listeners = []
        self.price_provider = PriceProvider()
        self._init_scraper()
    
    def _init_scraper(self):
        self.scraper = HTMLScraper('http://foresignal.com')
        self.scraper.line_validators.append(lambda line: line.startswith('<div class="symbol') and 'GMT' in line)
        self.scraper.regx.append(re.compile('<a href="/signals/.+\.php" style="text-decoration:none;">(?P<currency_pair>.+/.+)</a></span>'))
        self.scraper.regx.append(re.compile('<div class="status"><span class=".+text">(?P<action>.+)</span></div>'))
        self.scraper.regx.append(re.compile('</div>From (?P<from>.+)<br>Till (?P<to>.+)<div class="status">'))
        self.scraper.regx.append(re.compile('<img src="(?P<trend_img>/img/(buy|sell)\.png)">'))
        self.scraper.regx.append(re.compile('(Buy|Sell) at <span class=".+text"><font size="\+2"><script type="text/javascript">f\(\'(?P<price>.+)\'\);</script></font></span>'))
        self.scraper.converters['from'] = DateConverter()
        self.scraper.converters['to'] = self.scraper.converters['from']
        self.scraper.converters['price'] = PriceConverter()
    
    def process(self):
        try:
            content = self.scraper.fetch()
            regx_price_decoder_params = re.compile("var z='(?P<z>.+)';function f\(s\)\{var i=0;for \(i=0;i<s.length;i\+\+\)\{document.write\(z.charAt\(s.charCodeAt\(i\)-(?P<padding>\d+)-i\)\);\}\}")
            price_decoder_params = self.scraper.get_value(regx_price_decoder_params, content)
            self.scraper.converters['price'].set_params(**price_decoder_params)
            signals = self.scraper.get_values()
            signals = sorted(signals, key=lambda signal: signal['from'])
            map(self.process_signal, signals)
        except urllib2.URLError, e:
            print 'Error: signals cannot be loaded, reason: %s' % e.reason
    
    def _fire_event(self, event, signal):
        sig = signal.copy()
        key = signal['currency_pair']
        price = self.price_provider.get_price(key)
        sig['current_mid'] = price['mid'] if price else ''
        for listener in self.listeners:
            try:
                handler = getattr(listener, 'on_' + event)
                handler(sig)
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
    
    def close(self):
        self.price_provider.stop()
    
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
        return '%(currency_pair)s\n%(action)s -> %(price)s\n current price\n  mid: %(current_mid)s\n  valid\n  from: %(from)s\n  to:   %(to)s' % signal

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

    def _get_img_path(self, signal):
        img_path = '/tmp/%(action)s.png' % signal
        if not os.path.exists(img_path):
            img_url = 'http://foresignal.com%(trend_img)s' % signal
            img = urllib2.urlopen(img_url).read()
            open(img_path % signal, 'w').write(img)
        return img_path
        
    def _notify_pynotify(self, title, body, signal):    
        import pynotify
        n = pynotify.Notification(title, body, self._get_img_path(signal))
        n.set_urgency(pynotify.URGENCY_LOW)
        n.set_timeout(500) # 10 seconds
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
    setup, options = parse_command_line()
    foresignal = Foresignal(setup)
    try:
        foresignal.register(SignalPrinter())
        if options.notifications:
            foresignal.register(SignalNotifier())
        foresignal.start()
    except KeyboardInterrupt:
        pass
    foresignal.close()

if __name__ == '__main__':
    sys.exit(main())
