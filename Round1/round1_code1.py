import jsonpickle 
from datamodel import OrderDepth, UserId, TradingState, Order
from typing import Any, List, Dict
import math
import collections
from collections import defaultdict


Limit= 20

PRODUCT = ["AMETHYSTS","STARFRUIT"]
PRICE_AGGRESSION = 0 # determines how aggressively we hunt for values above and below the spread

THRESHOLDS = {
	"over": 0,
	"mid": 10
}
POSITION_LIMITS = {
	"AMETHYSTS": 20,
	"STARFRUIT": 20,
	"PRODUCT1": 10,
	"PRODUCT2": 20
}

POSITION_LIMIT = 20

STARFRUIT_COEFFICIENTS = [17.36384211, 0.34608026, 0.26269948, 0.19565408, 0.19213413]

class Trader:
	previous_starfruit_prices = []
	
	
	def update_starfruit_price_history(self, previousTradingState, tradingState: TradingState):
		if "previous_starfruit_prices" in previousTradingState:
			self.previous_starfruit_prices = previousTradingState["previous_starfruit_prices"]
		else:
			self.previous_starfruit_prices = []

		# get the current price and append it to the list
		lowest_sell_price = sorted(tradingState.order_depths["STARFRUIT"].sell_orders.keys())[0]
		highest_buy_price = sorted(tradingState.order_depths["STARFRUIT"].buy_orders.keys(), reverse=True)[0]

		current_mid_price = (lowest_sell_price + highest_buy_price) / 2

		self.previous_starfruit_prices.append(current_mid_price)

		if len(self.previous_starfruit_prices) > 4:
			self.previous_starfruit_prices.pop(0)


	def get_starfruit_price(self) -> float | None:
		# if we don't have enough data, return None
		if len(self.previous_starfruit_prices) < 4:
			return None

		# calculate the average of the last four prices

		print(STARFRUIT_COEFFICIENTS)
		print(self.previous_starfruit_prices)
		print(sum([STARFRUIT_COEFFICIENTS[i] * self.previous_starfruit_prices[i] for i in range(4)]))

		expected_price = STARFRUIT_COEFFICIENTS[0] + sum([STARFRUIT_COEFFICIENTS[i + 1] * self.previous_starfruit_prices[i] for i in range(4)])

		return expected_price

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
			return 10000
		if product == "STARFRUIT":
			return self.get_starfruit_price()
		return None
	
	def compute_order_Amethysts(self,bot_buy_order,bot_sell_order,curr_position):
			self.bot_buy_order=bot_buy_order
			self.bot_sell_order=bot_sell_order
			self.curr_position=curr_position
			order:Order=[]
			least_sell, first_value = next(iter(self.bot_sell_order.items()))
			highest_buy, first_value1 = next(iter(self.bot_sell_order.items()))
			mid_price=(least_sell+highest_buy)/2
			Total_Vol=0
			break_price=0
			temp_vol=0
			print(f"{self.curr_position} is the current position")
			if mid_price<10000:
				for i in self.bot_sell_order.keys():
					if i<10000:
						Total_Vol=Total_Vol-self.bot_sell_order[i]
					else:
						break_price=i
						break
				if (Limit-self.curr_position)<=Total_Vol:
						for ask,quant in self.bot_sell_order.items():
							if (temp_vol-quant)<=(Limit-self.curr_position):
								order.append(Order("AMETHYSTS",ask,-quant))
								temp_vol=temp_vol-quant
							elif (temp_vol-quant)>(Limit-self.curr_position):
								order.append(Order("AMETHYSTS",ask,(Limit-self.curr_position)-temp_vol))
								break
				elif (Limit-self.curr_position)>Total_Vol:
					for ask,quant in self.bot_sell_order.items():
						if(ask!=break_price):
							order.append(Order("AMETHYSTS",ask,-quant))
						else:
							break
			elif mid_price>10000:
				for i in self.bot_buy_order.keys():
					if i>10000:
						Total_Vol=Total_Vol+self.bot_buy_order[i]
					else:
						break_price=i
						break
				if (-(-Limit-self.curr_position))<=Total_Vol:
					for ask,quant in self.bot_buy_order.items():
						if (temp_vol+quant)<=(-(-Limit-self.curr_position)):
							order.append(Order("AMETHYSTS",ask,-(quant)))
							temp_vol=temp_vol+quant	
						else:
							order.append(Order("AMETHSTS",ask,-((-(-Limit-self.curr_position))-temp_vol)))
							break
				else:
					for ask,quant in self.bot_buy_order.items():
						if(ask!=break_price):
							order.append(Order("AMETHYSTS",ask,-quant))
						else:
							break
			elif mid_price==10000:
				if self.curr_position<0:
					order.append(Order("AMETHYSTS",10000,-(self.curr_position)))
				else:
					order.append(Order("AMETHYSTS",10000,-(self.curr_position)))
			return order
	def run(self, state: TradingState):
			try:
				previousStateData = jsonpickle.decode(state.traderData)
			except:
				previousStateData = {}
			self.update_starfruit_price_history(previousStateData, state)
			result={}
			for product in state.order_depths.keys():
				self.bot_orders:OrderDepth=state.order_depths[product]
				self.curr_position=state.position.get(product,0)
				self.sorted_bot_sell_order=collections.OrderedDict(sorted(self.bot_orders.sell_orders.items()))
				self.sorted_bot_buy_order=collections.OrderedDict(sorted(self.bot_orders.buy_orders.items(),reverse=True))
				if product=="AMETHYSTS":
					order:Order=self.compute_order_Amethysts(self.sorted_bot_buy_order,self.sorted_bot_sell_order,self.curr_position)
					result[product]=order
				elif product=="STARFRUIT":
					product_acceptable_price = self.get_acceptable_price(state, product)
					if product_acceptable_price is None:
						continue
					else:
						orders = self.get_orders(state, product_acceptable_price, product)
						result[product] = orders
			traderData = {"previous_starfruit_prices": self.previous_starfruit_prices} 
			print(result)
			serialisedTraderData = jsonpickle.encode(traderData)
			conversions = 0 # Don't fully understand conversions? Not really documented in the task description
			return result, conversions, serialisedTraderData          
	