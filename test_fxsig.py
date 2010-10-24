#!/usr/bin/python

import unittest
import fxsig
import datetime, time

#
# Test DefaultConverter
#
class TestDefaultConverter(unittest.TestCase):
    
    def setUp(self):
        self.converter = fxsig.DefaultConverter()
    
    def test_convert_None_value(self):
        #GIVEN
        value = None
        #WHEN
        actual = self.converter.convert(value)
        #THEN
        self.assertTrue(actual == None)

    def test_convert_Empty_value(self):
        #GIVEN
        value = ''
        #WHEN
        actual = self.converter.convert(value)
        #THEN
        self.assertEquals(actual, '')

    def test_convert_value(self):
        #GIVEN
        value = ' aBc 123 '
        #WHEN
        actual = self.converter.convert(value)
        #THEN
        self.assertEquals(actual, ' aBc 123 ')
#
# Test DateConverter
#
class TestDateConverter(unittest.TestCase):

    def setUp(self):
        self.converter = fxsig.DateConverter()
        
    def test_convert_None_value(self):
        #GIVEN
        value = None
        #WHEN
        actual = self.converter.convert(value)
        #THEN
        self.assertTrue(actual == None)
    
    def test_convert_Empty_value(self):
        #GIVEN
        value = ''
        #WHEN
        actual = self.converter.convert(value)
        #THEN
        self.assertTrue(actual == None)
    
    def test_convert_Blank_value(self):
        #GIVEN
        value = ' '
        #WHEN
        self.assertRaises(ValueError, self.converter.convert, value)

    def test_convert_Not_string_value(self):
        #GIVEN
        value = 123
        #WHEN
        self.assertRaises(TypeError, self.converter.convert, value)

    def test_convert_GMT_value(self):
        #GIVEN
        value = 'Oct, 22 14:41 GMT'
        this_year = datetime.datetime.now().year
        STDOFFSET = datetime.timedelta(seconds = -time.timezone)
        if time.daylight:
            DSTOFFSET = datetime.timedelta(seconds = -time.altzone)
        else:
            DSTOFFSET = STDOFFSET
        #WHEN
        actual = self.converter.convert(value)
        #THEN
        self.assertEquals(type(actual), datetime.datetime)
        self.assertEquals(actual, datetime.datetime(year=this_year, month=10, day=22, hour=14, minute=41) + DSTOFFSET)
#
# Test PriceConverter
#
class TestPriceConverter(unittest.TestCase):

    def setUp(self):
        self.converter = fxsig.PriceConverter()
        self.converter.set_params('12', '12')
        
    def test_convert_None_value(self):
        #GIVEN
        value = None
        #WHEN
        actual = self.converter.convert(value)
        #THEN
        self.assertTrue(actual == None)
    
    def test_convert_Empty_value(self):
        #GIVEN
        value = ''
        #WHEN
        actual = self.converter.convert(value)
        #THEN
        self.assertTrue(actual == None)
    
    def test_convert_Blank_value(self):
        #GIVEN
        value = ' '
        #WHEN
        self.assertRaises(ValueError, self.converter.convert, value)

    def test_convert_Not_string_value(self):
        #GIVEN
        value = 123
        #WHEN
        self.assertRaises(TypeError, self.converter.convert, value)

    def test_convert_missing_params_value(self):
        #GIVEN
        value = 'XXXX'
        self.converter = fxsig.PriceConverter()
        #WHEN
        self.assertRaises(AttributeError, self.converter.convert, value)

    def test_convert_value(self):
        #GIVEN
        value = 'DMMPLN'
        self.converter.set_params('716845203.9', 67)
        #WHEN
        actual = self.converter.convert(value)
        #THEN
        self.assertTrue(type(actual), float)
        self.assertEquals(actual, 1.3952)
        
if __name__ == '__main__':
    unittest.main()