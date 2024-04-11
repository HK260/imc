from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string
import numpy as np
import statistics
import math

class Trader:

    PRODUCTS = {
        'STARFRUIT': {"TIME": [], "DATA": [], "DELTAS": [0], "QUANTITY": 0, "PRICE": 0, "PLIMIT": 20, "STRATEGY": "LR", "LR_SIZE": 5},
        'AMETHYSTS': {"TIME": [], "DATA": [], "DELTAS": [0], "QUANTITY": 0, "PRICE": 0, "PLIMIT": 20, "STRATEGY": "LR", "LR_SIZE": 5}
        }

    strategies = ["LR", "PT", ]

    def run(self, state: TradingState):

        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))

        time = state.timestamp

        result = {}
        for product in state.order_depths:

            ### Game Function
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []

            ### Compute Regressions when sufficient data points
            if len(Trader.PRODUCTS[product]["TIME"]) > Trader.PRODUCTS[product]["LR_SIZE"]:
                Trader.PRODUCTS[product]["PRICE"] = Trader.compute_price_regression(product, time)

            print("Acceptable price : " + str(Trader.PRODUCTS[product]["PRICE"]))
            print("Current Quantity: " + str(Trader.PRODUCTS[product]["QUANTITY"]))
            print("Buy Order depth : " + str(len(order_depth.buy_orders)) + ", Sell order depth : " + str(len(order_depth.sell_orders)))
            print("Current Strategy: " + str(Trader.PRODUCTS[product]["STRATEGY"]))
            print("Current Delta: " + str(Trader.PRODUCTS[product]["DELTAS"][-1]))

            if Trader.PRODUCTS[product]["STRATEGY"] == "LR" and time > Trader.PRODUCTS[product]["LR_SIZE"] * 100 and Trader.PRODUCTS[product]["STRATEGY"] in Trader.strategies:
                ### BUY ORDERS
                if len(order_depth.sell_orders) != 0:
                    ask, ask_amount = list(order_depth.sell_orders.items())[0]
                    if int(ask) < Trader.PRODUCTS[product]["PRICE"]:
                        order = Trader.submit_order(product, "BUY", ask, ask_amount)
                        orders.append(order)

                ### SELL ORDERS
                if len(order_depth.buy_orders) != 0:
                    bid, bid_amount = list(order_depth.buy_orders.items())[0]
                    if int(bid) > Trader.PRODUCTS[product]["PRICE"]:
                        order = Trader.submit_order(product, "SELL", bid, bid_amount)
                        orders.append(order)

            # Trader.compute_momentum(product, 0.5, order_depth)

            ### Store prices + quantities
            if len(order_depth.buy_orders) != 0 and len(order_depth.sell_orders) != 0:
                observed_price = statistics.mean([Trader.weighted_average_price(order_depth.buy_orders), Trader.weighted_average_price(order_depth.sell_orders)])
                if len(Trader.PRODUCTS[product]["DATA"]) > 0:
                    Trader.PRODUCTS[product]["DELTAS"].append(Trader.PRODUCTS[product]["DATA"][-1] - observed_price)
                Trader.PRODUCTS[product]["DATA"].append(observed_price)
                Trader.PRODUCTS[product]["TIME"].append(time)

            result[product] = orders

        # String value holding Trader state data required.
        # It will be delivered as TradingState.traderData on next execution.
        traderData = "SAMPLE"

        # Sample conversion request. Check more details below.
        conversions = 1
        return result, conversions, traderData

    def submit_order(product, action, price, quantity):
        can_buy = Trader.PRODUCTS[product]["PLIMIT"] - Trader.PRODUCTS[product]["QUANTITY"]
        can_sell = Trader.PRODUCTS[product]["QUANTITY"] + Trader.PRODUCTS[product]["PLIMIT"]
        if action == "BUY":
            order_quantity = min(abs(quantity), can_buy)
            print(action, str(order_quantity) + "x", price)
            Trader.PRODUCTS[product]["QUANTITY"] = Trader.PRODUCTS[product]["QUANTITY"] + order_quantity
            return Order(product, price, order_quantity)
        if action == "SELL":
            order_quantity = min(abs(quantity), can_sell)
            print(action, str(order_quantity) + "x", price)
            Trader.PRODUCTS[product]["QUANTITY"] = Trader.PRODUCTS[product]["QUANTITY"] - order_quantity
            return Order(product, price, -order_quantity)

    def compute_price_regression(product, time):
        X = np.array(Trader.PRODUCTS[product]["TIME"][-Trader.PRODUCTS[product]["LR_SIZE"]:])
        y = np.array(Trader.PRODUCTS[product]["DATA"][-Trader.PRODUCTS[product]["LR_SIZE"]:])

        X = X[:, np.newaxis]
        X = np.hstack([np.ones_like(X), X])

        coefficients, _residuals, _rank, _s = np.linalg.lstsq(X, y, rcond=None)
        intercept, slope = coefficients

        return time * slope + intercept

    # def compute_momentum(product, threshold, order_depth):
    #     data = np.array(Trader.PRODUCTS[product]["DELTAS"][-10:])

    #     indicator = np.mean(data)
    #     current_std = np.std(data)

    #     print(indicator)

    #     if Trader.PRODUCTS[product]["STRATEGY"] == "LR":
    #         if indicator > threshold and Trader.PRODUCTS[product]["QUANTITY"] < Trader.PRODUCTS[product]["PLIMIT"]:
    #             Trader.solidify(product, order_depth)
    #             Trader.PRODUCTS[product]["STRATEGY"]  = "CALL"

    #         if indicator < -threshold and Trader.PRODUCTS[product]["QUANTITY"] < Trader.PRODUCTS[product]["PLIMIT"]:
    #             Trader.liquidate(product, order_depth)
    #             Trader.PRODUCTS[product]["STRATEGY"]  = "PUT"

    #     elif Trader.PRODUCTS[product]["STRATEGY"] == "CALL" and indicator < 0.35:
    #         Trader.liquidate(product, order_depth)
    #         Trader.PRODUCTS[product]["STRATEGY"] = "LR"

    #     elif Trader.PRODUCTS[product]["STRATEGY"] == "PUT" and indicator > -0.35:
    #         Trader.solidify(product, order_depth)
    #         Trader.PRODUCTS[product]["STRATEGY"] = "LR"

    def liquidate(product, order_depth):                                                            # SELL EVERYTHING
        for depth in range(0, len(order_depth.buy_orders)):
            if Trader.PRODUCTS[product]["QUANTITY"] <= -Trader.PRODUCTS[product]["PLIMIT"]:
                break
            bid, bid_amount = list(order_depth.buy_orders.items())[depth]
            Trader.submit_order(product, "SELL", bid, bid_amount)

    def solidify(product, order_depth):                                                             # BUY EVERYTHING
        for depth in range(0, len(order_depth.sell_orders)):
            if Trader.PRODUCTS[product]["QUANTITY"] >= Trader.PRODUCTS[product]["PLIMIT"]:
                break
            ask, ask_amount = list(order_depth.sell_orders.items())[depth]
            Trader.submit_order(product, "BUY", ask, ask_amount)

    def weighted_average_price(price_quantity_dict):
        total_quantity = sum(price_quantity_dict.values())
        total_value = sum(price * quantity for price, quantity in price_quantity_dict.items())

        if total_quantity == 0:
            return 0

        return total_value / total_quantity