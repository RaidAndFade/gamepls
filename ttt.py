import websockets
import asyncio
import random
import logging
logger = logging.getLogger('websockets.server')
logger.setLevel(logging.ERROR)
logger.addHandler(logging.StreamHandler())

conns = []

async def make_matches():
    global conns
    while True:
        for x in conns:
            if not x.matchable or not x.ws.open:
                continue
            others = [c for c in conns if c.game == x.game and c.lobby == x.lobby and c.matchable and c.ws.open and c is not x]
            if len(others)>0:
                y = others[0]
                x.matchable = y.matchable = False
                b = boards[x.game](x,y)
                x.board = y.board = b
                print("Found match between "+x.name+" and "+y.name)
                await b.start_match()
        await asyncio.sleep(1)

class TTTBoard:
    def __init__(self,p1,p2):
        self.p1=p1
        self.p2=p2
        self.make_board()
        self.finished=False
        self.turn = p1 if random.randint(0,100)>50 else p2
    
    def make_board(self):
        self.board = [None]*9

    async def start_match(self):
        await self.p1.ws.send("2"+self.p2.name)
        await self.p2.ws.send("2"+self.p1.name)
        await self.turn.ws.send("30")

    async def box_pick(self,pos,pl):
        if pl == self.turn and 0<=pos<=8:
            if await self.make_move(pos):
                await self.check_win()
                if not self.finished:
                    self.turn = self.p1 if self.turn == self.p2 else self.p2
                    await self.turn.ws.send("30")
        else:
            pass
            #other pl is cheating/hacking
    
    async def on_message(self,msg,pl):
        if msg[0] == "0":
            await self.box_pick(int(msg[1]),pl)

    async def player_won(self,pl,plcs):
        self.finished = True
        await self.p1.ws.send("32"+str([None,self.p1,self.p2].index(pl))+"".join(str(p) for p in plcs))
        await self.p2.ws.send("32"+str([None,self.p2,self.p1].index(pl))+"".join(str(p) for p in plcs))
        await self.p1.ws.close()
        await self.p2.ws.close()

    async def check_win(self):
        for x in range(3): # check all cols
            if self.board[x]==self.board[x+3]==self.board[x+6] and self.board[x] is not None:
               await self.player_won(self.board[x],[x,x+3,x+6])
               return

        for x in range(0,8,3): # check all rows
            if self.board[x]==self.board[x+1]==self.board[x+2] and self.board[x] is not None:
               await self.player_won(self.board[x],[x,x+1,x+2])
               return
        
        if self.board[0]==self.board[4]==self.board[8] and self.board[0] is not None: #topleft to botright
            await self.player_won(self.board[0],[0,4,8])
            return

        if self.board[2]==self.board[4]==self.board[6] and self.board[2] is not None: #topright to botleft
            await self.player_won(self.board[2],[2,4,6])
            return

        if self.board.count(None)==0: #tie, no more playable spots
            await self.player_won(None,[])
            return


    async def make_move(self,pos):
        if self.board[pos] is None:
            self.board[pos] = self.turn
            await self.p1.ws.send("31"+str(pos)+("1" if self.turn is self.p1 else "0"))
            await self.p2.ws.send("31"+str(pos)+("1" if self.turn is self.p2 else "0"))
            return True
        return False

boards = {
    "ttt": TTTBoard
}

class Connection:
    async def connpinger(self):
        while True:
            if not self.ws.open:
                return
            await self.ws.send("1")
            self.hb+=1
            if self.hb>3:
                await self.ws.close()
            await asyncio.sleep(1)

    async def connect(self):
        if not self.valid:
            await self.ws.close()
            return
        await self.ws.send("0")
        asyncio.get_event_loop().create_task(self.connpinger())
        try:
            async for m in self.ws:
                if m[0]=="0":
                    self.matchable=True
                    if len(m)==1 or m[1:].strip()=="":
                        await self.ws.close()
                    else:
                        self.name = m[1:][:32]
                        print(self.name + " joined the lobby <"+self.game+","+self.lobby+">")
                elif m[0]=="1":
                    self.hb = max(0,self.hb-1)
                elif m[0]=="3":
                    if self.board is not None:
                        await self.board.on_message(m[1:],self)
        except websockets.exceptions.WebSocketException as wse:
            pass
        if self.ws.open:
            await self.ws.close()
        self.matchable=False
        print(self.name + " has left <"+self.connip+">. ")

    def __init__(self,ws,path):
        self.board = None
        self.valid = True
        self.name = ""
        self.connip = ws.request_headers['x-forwarded-for'].split(",")[0]
        print("Conn from "+self.connip)
        pathparts = path.split("/")[1:]
        if len(pathparts) == 2:
            self.game,self.lobby = pathparts
        elif len(pathparts) == 1:
            self.game,self.lobby = pathparts[0],"none"
        else:
            self.valid = False
        self.hb=0
        self.ws = ws
        self.matchable=False

async def conn(ws, path):
    global conns
    c = Connection(ws,path)
    conns.append(c)
    await c.connect()

start_server = websockets.serve(conn, "0.0.0.0", 9999)

asyncio.ensure_future(start_server)
asyncio.ensure_future(make_matches())
asyncio.get_event_loop().run_forever()