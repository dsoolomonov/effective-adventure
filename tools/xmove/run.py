import os
env=dict(x.split(b'=',1) for x in open('/home/ubuntu/xmove/.env.run','rb').read().split(b'\0') if b'=' in x)
env={k.decode():v.decode() for k,v in env.items()}
os.chdir('/home/ubuntu/crude-oil-analytics')
os.execvpe('python3',['python3','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],env)
