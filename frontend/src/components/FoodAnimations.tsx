const bubbles = [0, 1, 2, 3, 4, 5];

export default function FoodAnimations() {
  return <div className="food-animations" aria-label="Animated Pizza Point food visuals">
    <div className="food-animation animation-fries"><img src="/images/food-animations/flying-fries.png" alt="Golden fries in a red fries packet"/></div>
    <div className="food-animation animation-cola"><img src="/images/food-animations/cola-splash.png" alt="Cola with ice and a liquid splash"/>{bubbles.map((index) => <i className={`cola-bubble bubble-${index}`} key={index}/>)}</div>
    <div className="food-animation animation-pizza"><img src="/images/food-animations/floating-pizza.png" alt="Floating pizza with melted cheese"/></div>
    <div className="food-animation animation-burger" aria-label="Opening burger"><img src="/images/food-animations/opening-burger.png" alt="Opening burger"/></div>
  </div>;
}
