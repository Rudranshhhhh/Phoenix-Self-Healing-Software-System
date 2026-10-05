"""Intentionally broken demo app: crashes with a KeyError."""
import time

PRODUCTS = {"apple": {"cost": 10}}


def get_product(name):
    product = PRODUCTS[name]
    return product["price"]


if __name__ == "__main__":
    print("broken-app starting", flush=True)
    time.sleep(2)
    print(get_product("apple"), flush=True)