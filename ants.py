
# objects:
#   1. map 800x800
#   2. entity 25x25
#   3. food 12x12

# game mechanics:
#   1. big circle in middle with +0.1/s
#   2. walls kills
#   3. collisions -1/s when delta > 3
#   4. food gives 1

import random
import math
import os
import importlib

from PIL import Image, ImageDraw, ImageFont
from pyglet.image import ImageData

import cocos
import cocos.actions as act
import cocos.euclid as eu
import cocos.collision_model as cm
from cocos.layer import Layer, ColorLayer
from cocos.sprite import Sprite
from cocos.text import Label
from cocos.director import director


class CircleEntity(Sprite):
    def __init__(self, size, color):
        super(CircleEntity, self).__init__(self.__create_image(size, color))
        self.__init_phys(size)
        self.life = 0

    def __create_image(self, size, color):
        im = Image.new('RGBA', (size, size), (255, 255, 255, 0))
        draw = ImageDraw.Draw(im)
        draw.ellipse((1, 1, im.size[0]-1, im.size[1]-1), fill=color)

        return ImageData(*im.size, 'RGBA', im.tobytes(), pitch=-im.size[0]*4)

    def __init_phys(self, size):
        self.cshape = cm.CircleShape(eu.Vector2(0, 0), size/2)

    def update(self, dt):
        self.cshape.center = eu.Vector2(*self.position)


class Player(CircleEntity):
    __SIZE = 25

    def __init__(self, name):
        color = self.__gen_rand_color()
        super(Player, self).__init__(self.__SIZE, color)

        self.life = 1
        self.name = name[:15]

        self.__label = Label()
        self.__label.element.color = color[:3] + (255,)
        self.__label.position = (self.__SIZE/2, self.__SIZE/2)
        self.add(self.__label)

    def __gen_rand_color(self):
        array = [random.random() for _ in range(3)]
        r = max(array)
        return tuple(int(255 * i/r) for i in array) + (200,)

    def update(self, dt):
        super(Player, self).update(dt)
        self.life -= 0.3 * dt

        self.__label.element.text = '{} -> {:.2f}'.format(self.name, self.life)

    def __str__(self):
        return 'Player:{}'.format(self.name)


class Feeder(CircleEntity):
    __SIZE = 80
    __COLOR = (128, 255, 128, 240)

    def __init__(self):
        super(Feeder, self).__init__(self.__SIZE, self.__COLOR)


class Food(CircleEntity):
    __SIZE = 12
    __COLOR = (255, 255, 0, 200)

    def __init__(self):
        super(Food, self).__init__(self.__SIZE, self.__COLOR)
        self.life = 1


class Main(ColorLayer):
    WIDTH = 800
    HEIGHT = 800
    __FOOD_COUNT = 8

    def __init__(self):
        super(Main, self).__init__(52, 152, 219, 70)
        self.collision_manager = cm.CollisionManagerBruteForce()

        self.__init_map()
        self.__init_food()
        self.__init_players()

        self.schedule(self.__update)

    def add(self, obj, *args, **kwargs):
        ''' Override add() that adds physical objects as well '''
        super(Main, self).add(obj, *args, **kwargs)
        if hasattr(obj, 'cshape'):
            self.collision_manager.add(obj)

    def __rand_position(self):
        return random.randrange(10, self.WIDTH-10), random.randrange(10, self.HEIGHT-10)

    def __init_map(self):
        self.feeder = Feeder()
        self.feeder.position = self.WIDTH//2, self.HEIGHT//2
        self.add(self.feeder, z=-1)

    def __init_players(self):
        self.__players = []

        for fn in os.listdir('ai'):
            if fn[:6] != 'player':
                continue

            mod_name = os.path.splitext(fn)[0]
            mod = importlib.import_module('ai.{}'.format(mod_name))
            ai = mod.Player()

            p = Player(ai.name)
            p.position = self.__rand_position()
            p.do(MoveAI(ai, self.__players, self.__food))

            self.__players.append(p)
            self.add(p)

    def __init_food(self):
        self.__food = []

        for i in range(self.__FOOD_COUNT):
            f = Food()
            f.position = self.__rand_position()
            self.__food.append(f)
            self.add(f, z=1)

    def __update(self, dt):
        # update physics positions
        self.feeder.update(dt)

        for p in self.__players:
            p.update(dt)

        for f in self.__food:
            f.update(dt)

        # check all collisions
        for c1, c2 in self.collision_manager.iter_all_collisions():
            if type(c1) is Player and type(c2) is Player:
                if c1.life > 0 and c2.life > 0 and math.fabs(c1.life - c2.life) > 1:
                    c1.life -= 2 * dt
                    c2.life -= 2 * dt
            elif type(c1) is Food and type(c2) is Player and c1.life > 0:
                c2.life += c1.life
                c1.life = 0
            elif type(c1) is Player and type(c2) is Food and c2.life > 0:
                c1.life += c2.life
                c2.life = 0
            elif type(c1) is Feeder and type(c2) is Player:
                c2.life += 0.1 * dt
            elif type(c1) is Player and type(c2) is Feeder:
                c1.life += 0.1 * dt

        # update lives
        dead_players = []
        for p in self.__players:
            if p.life <= 0:
                dead_players.append(p)

            if p.position[0] < 10 or p.position[0] > self.WIDTH-10 or p.position[1] < 10 or p.position[1] > self.HEIGHT-10:
                # players out of bounds are also dead
                dead_players.append(p)

        for p in dead_players:
            # removing from layer crashes with error at the moment, so just set them to an off-
            # screen position and remove from players list
            self.__players.remove(p)
            p.remove_action(p.actions[0])
            p.position = -100, -100

            print('{} died'.format(p))

        for f in self.__food:
            if f.life <= 0:
                # respawn it
                f.position = self.__rand_position()
                f.life = 1


class MoveAI(act.Move):
    __SPEED = 1.5

    def __init__(self, ai, players, food, *args, **kwargs):
        super(MoveAI, self).__init__(*args, **kwargs)
        self.__ai = ai
        self.__players = players
        self.__food = food

    def step(self, dt):
        try:
            dx, dy = self.__ai.update(
                [p.position for p in self.__players],
                [p.life for p in self.__players],
                [f.position for f in self.__food]
            )
        except:
            # any exception in user script results in a null movement vector
            print('{} threw exception'.format(self.target))
            dx, dy = 0, 0

        # normalize movement vector
        mag = (dx*dx + dy*dy) ** 0.5
        if math.fabs(mag) > 1e-6:
            dx /= mag
            dy /= mag

        self.target.position = (
            self.target.position[0] + dx * self.__SPEED,
            self.target.position[1] + dy * self.__SPEED
        )

        # inform the user scripts of their variables
        # NOTE: make copies, user scripts aren't allowed refs
        self.__ai.life = self.target.life
        self.__ai.position = self.target.position[:]

    def __deepcopy__(self, memo):
        # the cocos framework does a deepcopy on the action, and we need the players and food
        # refs to work in __init__ so this deepcopy override needs to be here
        return self


class PlayerAI:
    def __init__(self, name):
        self.name = name

        self.life = 0
        self.position = (0, 0)


if __name__ == '__main__':
    director.init(width=Main.WIDTH, height=Main.HEIGHT, autoscale=True, resizable=True)
    director.run(cocos.scene.Scene(Main()))
