import asyncio
import numpy
import cv2
import base64
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
import math
import time

users = set()
frame_dict = dict() # dictionary of all the users the their frames
blink_dict = dict()
viewer_connection = None
async def handler(websocket):

    actual_name = None
    count_frame = 0
    loop = asyncio.get_running_loop()

    # first name is sent to thru web
    try:
        name =  await websocket.recv()
    except(ConnectionClosed):
        print("Bye bye connection lost")
        return

    # if the connection happens to be a viewer one let it stay here and not go forward
    if name == "VIEWER":
        global viewer_connection
        viewer_connection = websocket
        print("Viewer Connected")
        try:
            await websocket.wait_closed()
        finally:
            print("Viewer disconnected")
        return

    # init important info about use
    actual_name = add_user(name)
    frame_dict[actual_name] = None      # create the frame dict but initially empty
    blink_dict[actual_name] = 0
    print(f"{actual_name} joined!")
    blink_count = 0
    while True:

        try:
            message = await websocket.recv()

            if message == "BLINK":
                blink_dict[actual_name]+=1
                print(f"{actual_name} BLINKED: {blink_dict[actual_name]}")
                continue
            header, coded=message.split(",",1)
            img_bytes = base64.b64decode(coded)
            arr = numpy.frombuffer(img_bytes,dtype=numpy.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            frame_dict[actual_name] = frame             # save the current frame in the dict

        except(ConnectionClosed):
            print("Bye bye connection lost")
            users.discard(actual_name)
            del frame_dict[actual_name]
            del blink_dict[actual_name]
            break



async def main():
    server = await serve(handler, "", 8001)
    asyncio.create_task(broadcast_grid_loop())
    await server.serve_forever()


def add_user(name : str):

    count = 1
    while True:
        if (name in users):
            if((name+str(count)) in users):
                count+=1
            else:
                users.add(name+str(count))
                return (name+str(count))
        else:
            users.add(name)
            return (name)


def create_grid(frames_dict, grid_width=1280, grid_height=720):

    frames = list((name,frame) for (name,frame) in frames_dict.items() if frame is not None)
    frame_num = len(frames)

    if frame_num == 0:
        return numpy.full((grid_height, grid_width, 3),fill_value=255, dtype=numpy.uint8)

    column_num = math.ceil(math.sqrt(frame_num))
    row_num = math.ceil(frame_num / column_num)

    tile_height = grid_height//row_num
    tile_width = grid_width//column_num

    # grid size initially all white
    grid = numpy.full((grid_height, grid_width, 3),fill_value=255 ,dtype=numpy.uint8)

    # add frames into grid
    count = 0
    for frame in frames:
        cv2.putText(frame[1], f"{blink_dict[frame[0]]}", (30, 30), cv2.FONT_HERSHEY_DUPLEX, 1, (0, 200, 0), 2)
        resized = cv2.resize(frame[1], (tile_width, tile_height))


        row = count // column_num
        col = count % column_num

        y_start = row * tile_height
        x_start = col * tile_width

        grid[y_start:y_start + tile_height, x_start:x_start + tile_width] = resized
        count+=1
    return grid

async def broadcast_grid_loop():
    loop = asyncio.get_running_loop()
    while True:

        start = time.time()
        grid = await loop.run_in_executor(None, create_grid, frame_dict)
        buffer = await loop.run_in_executor(None, encode_grid, grid)
        elapsed = time.time() - start

        img = "data:image/jpeg;base64," + buffer
        try:
            await viewer_connection.send(img)
        except:
            pass

        await asyncio.sleep(max(0, 0.05 - elapsed))

# conver image to format to send over websocket
def encode_grid(grid):
    success, buffer = cv2.imencode(".jpg", grid)
    encoded = base64.b64encode(buffer).decode("utf-8")
    return encoded

if __name__ == "__main__":
    asyncio.run(main())
