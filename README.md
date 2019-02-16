# fastapi-websocket-broadcast

An example of the familiar 'chat' websocket demo app, implemented in [FastAPI](https://github.com/tiangolo/fastapi) / [Starlette](https://github.com/encode/starlette).

## HTTP Endpoints

### GET /
Serves static HTML for chatroom.

### GET /list_users
Returns a JSON list of user IDs for users connected via websocket.

### POST /thunder
Broadcasts an ambient message to all users in the chatroom. Message is configurable via the `category` parameter; values should match the `Distance` enum.

## Websocket interface

Data from the server is JSON in the form

```json
{
    "type": ...,
    "data": {
        ...
    }
}
```

Where `type` is one of:

- **ROOM_JOIN** - sent to a user on successfully joining the chatroom
- **USER_JOIN** - sent to all chatroom users when a new user joins the chatroom
- **USER_LEAVE** - sent to all chatroom users when a user leaves the chatroom 
- **ERROR** - sent to one or more users in the event of a server error
- **MESSAGE** - chat message from one user, broadcast to all chatroom users
- **WHISPER** - private message from one user to another
