from g4f.client import Client
import gradio as gr
import re

# Initialize GPT client
client = Client()

# Function to get ingredients adjusted for number of servings
def get_scaled_ingredients(dish_name, servings):
    try:
        servings = int(servings)
        if servings <= 0:
            return "Please enter a positive number for servings."
    except:
        return "Invalid number of servings. Please enter a number."

    # Prompt for base ingredients (assume for 2 servings)
    prompt = f"""
You are a helpful chef bot. List the main ingredients and approximate quantities for the dish: {dish_name}, for 2 servings.
Use this format:
- Ingredient Name: Quantity (with units)
Keep it simple and consistent.
"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    gpt_output = response.choices[0].message.content

    # Extract and scale ingredients
    lines = gpt_output.strip().split("\n")
    ingredients = []
    scale_factor = servings / 2  # since GPT gave ingredients for 2 servings

    for line in lines:
        if line.startswith("-"):
            try:
                name, quantity = line[2:].split(":", 1)
                name = name.strip()
                quantity = quantity.strip()

                # Try to extract numeric value to scale
                match = re.match(r"([\d\.\/]+)\s*(.*)", quantity)
                if match:
                    amount_str, unit = match.groups()
                    # Convert fractions to float
                    try:
                        amount = eval(amount_str)
                        scaled_amount = round(amount * scale_factor, 2)
                        scaled_quantity = f"{scaled_amount} {unit}".strip()
                    except:
                        scaled_quantity = quantity  # fallback
                else:
                    scaled_quantity = quantity  # no scaling possible

                ingredients.append(f"{name}: {scaled_quantity}")
            except:
                continue

    ingredient_text = f"Ingredients for {servings} serving(s) of {dish_name}:\n" + "\n".join(ingredients)
    return ingredient_text

# Gradio Interface
interface = gr.Interface(
    fn=get_scaled_ingredients,
    inputs=[
        gr.Textbox(lines=1, placeholder="Enter a dish name (e.g., Biryani, Pasta)"),
        gr.Textbox(lines=1, placeholder="Number of servings", label="Servings")
    ],
    outputs="text",
    title="🍽️ Scalable Ingredient Finder",
    description="Enter a dish and how many people you're serving. Get scaled ingredient quantities powered by GPT-4."
)

if __name__ == '__main__':
    interface.launch()
