# coding: utf-8
"""Demonstration of websocket chat app using FastAPI, Starlette, and an in-memory
broadcast backend.
"""

from typing import List

from fastapi import FastAPI
from pydantic import BaseModel
from starlette.endpoints import WebSocketEndpoint
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.types import ASGIApp, ASGIInstance, Scope
from starlette.websockets import WebSocket


app = FastAPI()     # pylint: disable=invalid-name
app.debug = True


@app.on_event('startup')
async def start_room():
    global chat_room
    app.chat_room = Room()


class Room:
    """Room state, comprising connected users.
    """
    def __init__(self):
        self._users = {}

    def __len__(self) -> int:
        """Get the number of users in the room.
        """
        return len(self._users)

    @property
    def empty(self):
        """Check if the room is empty.
        """
        return len(self._users) == 0

    @property
    def user_list(self) -> List[str]:
        """Return a list of IDs for connected users.
        """
        return list(self._users)

    def add_user(self, user_id: str, websocket: WebSocket):
        """Add a user websocket, keyed by corresponding user ID.

        Raises:
            ValueError: If the `user_id` already exists within the room.
        """
        if user_id in self._users:
            raise ValueError(f'User {user_id} is already in the room')
        self._users[user_id] = websocket

    def remove_user(self, user_id):
        """Remove a user from the room.

        Raises:
            ValueError: If no such user is stored in the room.
        """
        if user_id not in self._users:
            raise ValueError(f'User {user_id} is not in the room')
        del self._users[user_id]

    async def broadcast_message(self, user_id: str, msg: str):
        """Broadcast message to all connected users.
        """
        for websocket in self._users.values():
            await websocket.send_json({
                'type': 'MESSAGE',
                'data': {
                    'user_id': user_id,
                    'msg': msg,
                }
            })

    async def broadcast_user_joined(self, user_id: str):
        """Broadcast message to all connected users.
        """
        for websocket in self._users.values():
            await websocket.send_json({
                'type': 'USER_JOIN',
                'data': user_id, 
            })

    async def broadcast_user_left(self, user_id: str):
        """Broadcast message to all connected users.
        """
        for websocket in self._users.values():
            await websocket.send_json({
                'type': 'USER_LEAVE',
                'data': user_id, 
            })


class RoomEventMiddleware:
    """Middleware for providing a global :class:`~.Room` instance to both HTTP
    and WebSocket scopes.

    Although it might seem odd to load the broadcast interface like this (as
    opposed to, e.g. providing a global) this both mimics the pattern
    established by starlette's existing DatabaseMiddlware, and describes a
    pattern for installing an arbitrary broadcast backend (Redis PUB-SUB,
    Postgres LISTEN/NOTIFY, etc) and providing it at the level of an individual
    request.
    """
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._room = Room()

    def __call__(self, scope: Scope) -> ASGIInstance:
        if scope['type'] in ('lifespan', 'http', 'websocket'):
            scope['room'] = self._room
        return self.app(scope)


app.add_middleware(RoomEventMiddleware)


@app.get('/')
def home():
    return FileResponse('static/index.html')


@app.get('/list_users')
async def list_users(request: Request):
    """Broadcast an ambient message to all chat room users.
    """
    return request.get('room').user_list


class Distance(BaseModel):
    """Indicator of distance for /thunder endpoint.
    """
    category: str = 'extreme'


@app.post('/thunder')
async def thunder(request: Request, distance: Distance=None):
    """Broadcast an ambient message to all chat room users.
    """
    wsp = request.get('room')
    if distance.category == 'near':
        await wsp.broadcast_message('server', 'Thunder booms overhead')
    elif distance.category == 'far':
        await wsp.broadcast_message('server', 'Thunder rumbles in the distance')
    else:
        await wsp.broadcast_message('server', 'You feel a faint tremor')
    return {
        'broadcast': distance
    }


@app.websocket_route('/ws', name='ws')
class RoomLive(WebSocketEndpoint):
    """Live connection to the global :class:`~.Room` instance, via WebSocket.
    """
    encoding = 'text'
    session_name = ''
    count = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room = None
        self.user_id = None

    @classmethod
    def get_next_user_id(cls):
        """Returns monotonically increasing numbered usernames in the form
            'user_[number]'
        """
        user_id = f'user_{cls.count}'
        cls.count += 1
        return user_id

    async def on_connect(self, websocket):
        """Handle a new connection.

        New users are assigned a user ID and notified of the room's connected
        users. The other connected users are notified of the new user's arrival,
        and finally the new user is added to the global :class:`~.Room` instance.
        """
        room = self.scope.get('room')
        if room is None:
            raise RuntimeError(f'Global `Room` instance unavailable!')
        self.room = room
        self.user_id = self.get_next_user_id()
        await websocket.accept()
        await websocket.send_json({
            'type': 'ROOM_JOIN',
            'data': {
                'user_id': self.user_id,
            }
        })
        await self.room.broadcast_user_joined(self.user_id)
        self.room.add_user(self.user_id, websocket)

    async def on_disconnect(self, _websocket: WebSocket, _close_code: int):
        """Disconnect the user, removing them from the :class:`~.Room`, and
        notifying the other users of their departure.
        """
        self.room.remove_user(self.user_id)
        await self.room.broadcast_user_left(self.user_id)

    async def on_receive(self, _websocket: WebSocket, msg: str):
        """Handle incoming message: `msg` is forwarded straight to `broadcast_message`.
        """
        await  self.room.broadcast_message(self.user_id, msg)
