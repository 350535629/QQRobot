# coding: utf-8

import os
import sys
import json
sys.path.insert(0, '../..')
import functools


# from celeryMQ.app import qqrobotMQ
from .utils import HTTPRequest, create_logger, bknHash
from .show_qrcode import QRcode
#from celeryMQ.reuse_methods import task_method

from .tulingapi import tuling,robot_name

class BaseSession(object):
    """提供封装后的Web QQ接口
    """
    def __init__(self):
        self.http = HTTPRequest()
        self.log = create_logger()
        self.msg_handle_map = {}

    def get_QRcode(self):
        QRcode_url = (
            "https://ssl.ptlogin2.qq.com/ptqrshow?"
            "appid=501004106&e=0&l=M&s=5&d=72&v=4&t=0.1"
        )
        response = self.http.get(QRcode_url).content
        with open("./QRcode.png", 'wb') as qrcode:
            qrcode.write(response)

        # TODO: async run
        QRcode("./QRcode.png").show()
        os.remove('./QRcode.png')

    def is_login(self):
        """扫码登录轮循获取登录状态
        """
        url = ("https://ssl.ptlogin2.qq.com/ptqrlogin?"
               "ptqrtoken={0}&webqq_type=10&"
               "remember_uin=1&login2qq=1&aid=501004106&u1=http%3A%2F"
               "%2Fw.qq.com%2Fproxy.html%3Flogin2qq%3D1%26webqq_type%"
               "3D10&ptredirect=0&ptlang=2052&daid=164&from_ui=1&pttype=1&"
               "dumy=&fp=loginerroralert&action=0-0-8449&mibao_css=m_webqq&"
               "t=1&g=1&js_type=0&js_ver=10216&login_sig=&"
               "pt_randsalt=2".format(
                   bknHash(self.http.session.cookies.get('qrsig'), init_str=0)
               ))
        self.http.session.headers['Referer'] = (
            "https://ui.ptlogin2.qq.com/cgi-bin/login?daid=164&target=self&"
            "style=16&mibao_css=m_webqq&appid=501004106&enable_qlogin=0&"
            "no_verifyimg=1&s_url=http%3A%2F%2Fw.qq.com%2Fproxy.html&"
            "f_url=loginerroralert&strong_login=1&login_state=10&t=20131024001"
        )
        response = self.http.get(url).text
        self.Ptwebqq_url = response.split("','")[2]
        # TODO: 保存cookie至本地
#        self.save_cookies()
        return response

    def get_ptwebqq(self):
        """获取ptwebqq参数
        """
        self.http.get(self.Ptwebqq_url, timeout=60)
        self.ptwebqq = self.http.session.cookies['ptwebqq']
        return self.ptwebqq

    def get_vfwebqq(self):
        vfwebqq_url = ("http://s.web2.qq.com/api/getvfwebqq?"
                       "ptwebqq={0}&clientid=53999199&psessionid=&"
                       "t=0.1".format(self.ptwebqq))
        self.http.session.headers['Referer'] = \
            "http://s.web2.qq.com/proxy.html?v=20130916001&callback=1&id=1"
        self.http.session.headers['Origin'] = 'http://s.web2.qq.com'
        vfw_res = self.http.get(vfwebqq_url, timeout=60).text
        self.vfwebqq = json.loads(vfw_res)['result']['vfwebqq']
        return self.vfwebqq

    def get_psessionid(self):
        api_url = 'http://d1.web2.qq.com/channel/login2'
        self.http.session.headers.update(
            {
                'Host': 'd1.web2.qq.com',
                "Origin": "http://d1.web2.qq.com",
                "Referer": (
                    "http://d1.web2.qq.com/proxy.html?"
                    "v=20151105001&callback=1&id=2")
            }
        )
        form_data = {
            'r': json.dumps(
                {
                    "ptwebqq": self.ptwebqq,
                    "clientid": 53999199,
                    "psessionid": '',
                    "status": "online"
                }
            )
        }
        pse_res = self.http.post(api_url, data=form_data).text
        result = json.loads(pse_res)['result']
        self.psessionid, self.uin = result['psessionid'], result['uin']
        return self.psessionid

    def parse_poll_res(self, msg):
        if 'error' in msg:
            return
        msg_dict = json.loads(msg)
        tmp_res = msg_dict.get('result')[0].get('value')
        msg_content = tmp_res.get('content')[-1]
        from_uin = tmp_res.get('from_uin')
        msg_type = msg_dict.get('result')[0].get('poll_type')
        if msg_type == 'group_message':
            name = robot_name()
            if name in msg_content:
                msg_group = tmp_res.get('group_code')
                msg_sender = tmp_res.get('send_uin')
                return (msg_content, msg_group, msg_type)
            else:
                return
        return (msg_content, from_uin, msg_type)

    def poll(self):
        poll_url = 'http://d1.web2.qq.com/channel/poll2'
        form_data ={'r': json.dumps(
            {
                "ptwebqq": self.ptwebqq,
                "clientid": 53999199,
                "psessionid": self.psessionid,
                "key": ''
            })}
        poll_res = self.http.post(poll_url, data=form_data).text
        fmsg = self.parse_poll_res(poll_res) # 解析轮循结果
        # msg_pre_handle = self.msg_handle_map.get(fmsg[0])
        # if fmsg and msg_pre_handle: # 检查收到的消息是否注册，注册直接回复
        #     self.send_msg.delay(msg=msg_pre_handle, receive_id=fmsg[1], msg_type=fmsg[2])
        if fmsg:
            self.log.info("{0}的{1} 发来一条消息: {2}".format(fmsg[1], fmsg[2], fmsg[0]))
        #     self.log.info("回复{0}: {1}".format(fmsg[1], msg_pre_handle))
        #     return None
        # else:
        #     return fmsg
        return fmsg

    def send_msg(self, msg, receive_id, msg_type, *args, **kw):
        msg = self.msg_handle_map.get(msg, msg)
        msg = tuling(msg)
        if msg_type == 'message':
            send_url = 'http://d1.web2.qq.com/channel/send_buddy_msg2'
            form_data = {
                'r': json.dumps({
                    'to': receive_id,
                    'content': json.dumps(
                        [msg,
                         ["font", {'name': "宋体", "size": 10,
                                    "style": [0, 0, 0], "color": "000000"}
                        ]]),
                    'face': 729,
                    'clientid': 53999199,
                    'msg_id': 34220099,
                    'psessionid': self.psessionid
                })
            }
            send_res = self.http.post(send_url, data=form_data).text
            self.log.info("回复{0}: {1}".format(receive_id, msg))
            return send_res
        else:
            # TODO: 根据消息类型分类处理
            #添加对群消息的回复
            if msg_type == 'group_message':
                send_url = 'http://d1.web2.qq.com/channel/send_qun_msg2'
                form_data = {
                    'r': json.dumps({
                        'group_uin': receive_id,
                        'content': json.dumps(
                            [msg,
                                ["font", {'name': "宋体", "size": 10,
                                          "style": [0,0,0], "color": "000000"}
                                ]]),
                        'face':729,
                        'clientid': 53999199,
                        'msg_id': 34220099,
                        'psessionid': self.psessionid
                    })
                }
                send_res = self.http.post(send_url, data=form_data).text
                self.log.info("回复{0}: {1}".format(receive_id, msg))
            return send_res

    def register_msg(self, msg, type='message'):
        """提供消息注册

            @bot.register("hello", type='message')
            def hello():
                '''函数返回值即回复内容
                '''
                # some other action
                return "reply hello"

        """
        def handle(func):
            # @functools.wraps(func)
            # def wrap(*args, **kw):
            # TODO: 更完善的消息处理机制
            # 此处应该在send_msg 方法内处理回复，send_msg 为异步方法，优化性能
            reply = func()
            self.msg_handle_map[msg] = reply
        return handle
