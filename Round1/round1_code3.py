import jsonpickle
from datamodel import OrderDepth, UserId, TradingState, Order
from typing import Any, List, Dict
import math
import collections
import numpy as np

# Note - all PRODUCT1 and PRODUCT2 strings are for unit testing purposes only.

POSITION_LIMIT = 20

POSITION_LIMITS = {
	"AMETHYSTS": 20,
	"STARFRUIT": 20,
	"PRODUCT1": 10,
	"PRODUCT2": 20
}

PRICE_AGGRESSION = 0 # determines how aggressively we hunt for values above and below the spread

THRESHOLDS = {
	"over": 0,
	"mid": 10
}


class Trader:
	previous_starfruit_prices_Starfruit= []
	previous_starfruit_prices_AMETHYSTS=[]

	def update_starfruit_price_history(self, previousTradingState, tradingState: TradingState):
		if "previous_starfruit_prices" in previousTradingState and "previous_Amethysts_prices" in previousTradingState:
			self.previous_starfruit_prices_Starfruit = previousTradingState["previous_starfruit_prices"]
			self.previous_starfruit_prices_AMETHYSTS = previousTradingState["previous_Amethysts_prices"]
		else:
			self.previous_starfruit_prices_AMETHYSTS=[]
			self.previous_starfruit_prices_Starfruit=[]
			
		# get the current price and append it to the list
		lowest_sell_price_Starfruit= sorted(tradingState.order_depths["STARFRUIT"].sell_orders.keys())[0]
		highest_buy_price_Starfruit= sorted(tradingState.order_depths["STARFRUIT"].buy_orders.keys(), reverse=True)[0]
		lowest_sell_price_Amethysts= sorted(tradingState.order_depths["AMETHYSTS"].sell_orders.keys())[0]
		highest_buy_price_Amethysts= sorted(tradingState.order_depths["AMETHYSTS"].buy_orders.keys(), reverse=True)[0]

		current_mid_price_Starfruit = (lowest_sell_price_Starfruit + highest_buy_price_Starfruit) / 2
		current_mid_price_Amethysts = (lowest_sell_price_Amethysts + highest_buy_price_Amethysts) / 2
		if len(self.previous_starfruit_prices_Starfruit) < 25:
			self.previous_starfruit_prices_Starfruit.append(current_mid_price_Starfruit)
		if len(self.previous_starfruit_prices_AMETHYSTS) <25:
			self.previous_starfruit_prices_AMETHYSTS.append(current_mid_price_Amethysts)
		curr_prices=[current_mid_price_Starfruit,current_mid_price_Amethysts]
		return curr_prices

	def get_starfruit_price(self) -> float | None:
		# if we don't have enough data, return None
		if len(self.previous_starfruit_prices_Starfruit) < 25:
			return None
		
		x_values=np.arange(1,26)
		y_values=np.array(self.previous_starfruit_prices_Starfruit)
		x_mean=np.mean(x_values)
		y_mean=np.mean(y_values)
		numerator=np.sum((x_values-x_mean)*(y_values-y_mean))
		denominator=np.sum((x_values-x_mean)**2)
		slope=numerator/denominator
		intercept = y_mean - slope * x_mean
		expected_value=slope*26+intercept
		print(self.previous_starfruit_prices_Starfruit)
		print(expected_value)
		return expected_value
	
	def get_Amethysts_price(self) -> float | None:
		if len(self.previous_starfruit_prices_AMETHYSTS)<25:
			return 10000
		else:
			x_values=np.arange(1,26)
			y_values=np.array(self.previous_starfruit_prices_AMETHYSTS)
			x_mean=np.mean(x_values)
			y_mean=np.mean(y_values)
			numerator=np.sum((x_values-x_mean)*(y_values-y_mean))
			denominator=np.sum((x_values-x_mean)**2)
			slope=numerator/denominator
			intercept=y_mean-slope*x_mean
			expected_value=0.0
			expected_value=slope*26+intercept
			print(self.previous_starfruit_prices_AMETHYSTS)
			print(expected_value)
			return expected_value

	def get_orders(self, state: TradingState, acceptable_price: int | float, product: str) -> List[Order]:
		# market taking + making based on Stanford's 2023 entry
		product_order_depth = state.order_depths[product]
		product_position_limit = POSITION_LIMITS[product]
		acceptable_buy_price = math.floor(acceptable_price)
		acceptable_sell_price = math.ceil(acceptable_price)
		orders = []
		
		# sort the order books by price (will sort by the key by default)
		orders_sell = sorted(list(product_order_depth.sell_orders.items()), key = lambda x: x[0])
		orders_buy = sorted(list(product_order_depth.buy_orders.items()), key=lambda x: x[0], reverse=True)
		
		lowest_sell_price = orders_sell[0][0]
		lowest_buy_price = orders_buy[0][0]

		# we start with buying - using our current position to determine how much and how aggressively we buy from the market

		buying_pos = state.position.get(product, 0)
		print(f"{product} current buying position: {buying_pos}")

		for ask, vol in orders_sell:
			# skip if there is no quota left
			if product_position_limit - buying_pos <= 0:
				break

			if ask < acceptable_price - PRICE_AGGRESSION:
				# we want to buy
				buy_amount = min(-vol, product_position_limit - buying_pos)
				buying_pos += buy_amount
				assert(buy_amount > 0)
				orders.append(Order(product, ask, buy_amount))
				print(f"{product} buy order 1: {vol} at {ask}")

			# if overleveraged, buy up until we are no longer leveraged
			if ask == acceptable_buy_price and buying_pos < 0:
				buy_amount = min(-vol, -buying_pos)
				buying_pos += buy_amount
				assert(buy_amount > 0)
				orders.append(Order(product, ask, buy_amount))
				print(f"{product} buy order 2: {vol} at {ask}")


		# once we exhaust all profitable sell orders, we place additional buy orders
		# at a price acceptable to us
		# what that price looks like will depend on our position
		
		if product_position_limit - buying_pos > 0: # if we have capacity
			if buying_pos < THRESHOLDS["over"]: # if we are overleveraged to sell, buy at parity for price up to neutral position
				target_buy_price = min(acceptable_buy_price, lowest_buy_price + 1)
				vol = -buying_pos + THRESHOLDS["over"]
				orders.append(Order(product, target_buy_price, vol))
				print(f"{product} buy order 3: {vol} at {target_buy_price}")
				buying_pos += vol
			if THRESHOLDS["over"] <= buying_pos <= THRESHOLDS["mid"]:
				target_buy_price = min(acceptable_buy_price - 1, lowest_buy_price + 1)
				vol = -buying_pos + THRESHOLDS["mid"] # if we are close to neutral
				orders.append(Order(product, target_buy_price, vol))
				print(f"{product} buy order 4: {vol} at {target_buy_price}")
				buying_pos += vol
			if buying_pos >= THRESHOLDS["mid"]:
				target_buy_price = min(acceptable_buy_price - 3, lowest_buy_price + 1)
				vol = product_position_limit - buying_pos
				orders.append(Order(product, target_buy_price, vol))
				print(f"{product} buy order 5: {vol} at {target_buy_price}")
				buying_pos += vol
				
		# now we sell - we reset our position
		selling_pos = state.position.get(product, 0)

		print(f"{product} current selling position: {selling_pos}")

		for bid, vol in orders_buy:
			# positive orders in the list
			# but we are sending negative sell orders, so we negate it
			# max we can sell is -product_position_limit - current position
			# if current position is negative we can sell less - if positive we can sell more
			
			if -product_position_limit - selling_pos >= 0:
				break

			if bid > acceptable_price + PRICE_AGGRESSION:
				sell_amount = max(-vol, -product_position_limit - selling_pos)
				selling_pos += sell_amount
				assert(sell_amount < 0)
				orders.append(Order(product, bid, sell_amount))
				print("{product} sell order 1: ", sell_amount, bid)
		
			# if at parity, sell up until we are no longer leveraged
			if bid == acceptable_sell_price and selling_pos > 0:
				sell_amount = max(-vol, -selling_pos)
				selling_pos += sell_amount
				assert(sell_amount < 0)
				orders.append(Order(product, bid, sell_amount))
				print("{product} sell order 2: ", sell_amount, bid)

		# start market making with remaining quota
		# if selling_pos
		if -product_position_limit - selling_pos < 0:
			if selling_pos > -THRESHOLDS["over"]:
				target_sell_price = max(acceptable_sell_price, lowest_sell_price - 1)
				vol = -selling_pos - THRESHOLDS["over"]
				orders.append(Order(product, target_sell_price, vol))
				selling_pos += vol
				print(f"{product} sell order 3: selling {vol} at {target_sell_price}")
			if -THRESHOLDS["over"] >= selling_pos >= -THRESHOLDS["mid"]:
				target_sell_price = max(acceptable_sell_price + 1, lowest_sell_price - 1)
				vol = -selling_pos - THRESHOLDS["mid"]
				orders.append(Order(product, target_sell_price, vol))
				selling_pos += vol
				print(f"{product} sell order 4: selling {vol} at {target_sell_price}")
			if -THRESHOLDS["mid"] >= selling_pos:
				target_sell_price = max(acceptable_sell_price + 2, lowest_sell_price - 1)
				vol = -product_position_limit - selling_pos
				orders.append(Order(product, target_sell_price, vol))
				selling_pos += vol
				print(f"{product} sell order 5: selling {vol} at {target_sell_price}")
				
		return orders
	
	def get_acceptable_price(self, state: TradingState, product: str) -> int | float | None:
		if product == "AMETHYSTS":
			return self.get_Amethysts_price()
		if product == "STARFRUIT":
			return self.get_starfruit_price()
		return None


	def run(self, state: TradingState):
		try:
			previousStateData = jsonpickle.decode(state.traderData)
		except:
			previousStateData = {}
		current_prices=self.update_starfruit_price_history(previousStateData, state)

		result = {}

		for product in state.order_depths:
			product_acceptable_price = self.get_acceptable_price(state, product)
			if product_acceptable_price is None:
				continue
			else:
				orders = self.get_orders(state, product_acceptable_price, product)
				result[product] = orders
		if len(self.previous_starfruit_prices_Starfruit)==25:
			self.previous_starfruit_prices_Starfruit.append(current_prices[0])
			self.previous_starfruit_prices_Starfruit.pop(0)
		if len(self.previous_starfruit_prices_AMETHYSTS)==25:
			self.previous_starfruit_prices_AMETHYSTS.append(current_prices[1])
			self.previous_starfruit_prices_AMETHYSTS.pop(0)
		
		traderData = {
			"previous_starfruit_prices": self.previous_starfruit_prices_Starfruit,
			"previous_Amethysts_prices":self.previous_starfruit_prices_AMETHYSTS
		} 

		print(result)

		serialisedTraderData = jsonpickle.encode(traderData)

		conversions = 0 # Don't fully understand conversions? Not really documented in the task description

		return result, conversions, serialisedTraderData
