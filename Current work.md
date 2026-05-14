1)  OCR word extraction failed: (3221225786, 'Estimating resolution as 123 ObjectCache(00007ffb276c6600)::~ObjectCache(): WARNING! LEAK! object 000001f28d17ef40 still has count 1 (id C:\\Users\\nagun\\AppData\\Local\\Programs\\Tesseract-OCR/tessdata/eng.traineddatalstm-punc-dawg) ObjectCache(00007ffb276c6600)::~ObjectCache(): WARNING! LEAK! object 000001f28eaee500 still has count 1 (id C:\\Users\\nagun\\AppData\\Local\\Programs\\Tesseract-OCR/tessdata/eng.traineddatalstm-word-dawg) ObjectCache(00007ffb276c6600)::~ObjectCache(): WARNING! LEAK! object 000001f28eaeec80 still has count 1 (id C:\\Users\\nagun\\AppData\\Local\\Programs\\Tesseract-OCR/tessdata/eng.traineddatalstm-number-dawg)') what is this fix that issue 
2) 22:54:36 | INFO     | Calendar events committed: ['https://www.google.com/calendar/event?eid=ZzMzb3RudmloNjdja2Fra3BkcHR1MXVqbzggbmFndW5pa2hpbDEyM0Bt', 'https://www.google.com/calendar/event?eid=MWpnc2Rva21yZnFuNW1nb2dibzA3czc4amcgbmFndW5pa2hpbDEyM0Bt', 'https://www.google.com/calendar/event?eid=bGVzYTBxZjQ2OTU2YXByMTJvdG1xZDZlc3MgbmFndW5pa2hpbDEyM0Bt', 'https://www.google.com/calendar/event?eid=aTNoZWM1YzMzbGY3Y2lmbmMydW5tZ3UyZjggbmFndW5pa2hpbDEyM0Bt', 'https://www.google.com/calendar/event?eid=c3U1MjcxOWJxODVuZzA2MTNpZWU2bGFqZGsgbmFndW5pa2hpbDEyM0Bt', 'https://www.google.com/calendar/event?eid=ZGc1ZmQ4YzJpaXVxNHBzMHJsNGtoOXRuaTQgbmFndW5pa2hpbDEyM0Bt']
Exception in thread Thread-144 (balloon_tip):
Traceback (most recent call last):
  File "C:\Users\nagun\AppData\Local\Python\pythoncore-3.14-64\Lib\threading.py", line 1082, in _bootstrap_inner
    self._context.run(self.run)
    ~~~~~~~~~~~~~~~~~^^^^^^^^^^
  File "C:\Users\nagun\AppData\Local\Python\pythoncore-3.14-64\Lib\threading.py", line 1024, in run
    self._target(*self._args, **self._kwargs)
    ~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\nagun\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\plyer\platforms\win\libs\balloontip.py", line 206, in balloon_tip
    WindowsBalloonTip(**kwargs)
    ~~~~~~~~~~~~~~~~~^^^^^^^^^^
  File "C:\Users\nagun\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\plyer\platforms\win\libs\balloontip.py", line 139, in __init__
    self.notify(title, message, app_name)
    ~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\nagun\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\plyer\platforms\win\libs\balloontip.py", line 179, in notify
    notify_data = win_api_defs.get_NOTIFYICONDATAW(
        0, self._hwnd,
    ...<2 lines>...
        self._balloon_icon
    )
  File "C:\Users\nagun\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\plyer\platforms\win\libs\win_api_defs.py", line 93, in get_NOTIFYICONDATAW
    notify_data = NOTIFYICONDATAW(*largs)
ValueError: string too long (308, maximum length 256) look at this and other possible problmes 
3) The overwheliming amount of notification and back log is anoying 
4) The form filler still requires work to do done on it 
5) The clandere thing should only work if after the pressing of its key do not have it constantly run 

