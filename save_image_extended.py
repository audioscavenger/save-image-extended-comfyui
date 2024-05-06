import os
import re
import sys
import json
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import numpy as np
import locale
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), 'comfy'))
original_locale = locale.setlocale(locale.LC_TIME, '')

import folder_paths
import pprint

# class SaveImageExtended -------------------------------------------------------------------------------
class SaveImageExtended:
  type = 'output'
  # counter_position = ['last', 'first', 'in filename_keys'] hmmmm not yet
  counter_position = ['last', 'first', 'in filename_keys']
  extToRemove = ['.safetensors', '.ckpt', '.pt']
  png_compress_level = 9

  def __init__(self):
    self.output_dir = folder_paths.get_output_directory()
    self.prefix_append = ''
  
  
  """
  Return a dictionary which contains config for all input fields.
  Some types (string): "MODEL", "VAE", "CLIP", "CONDITIONING", "LATENT", "IMAGE", "INT", "STRING", "FLOAT".
  Input types "INT", "STRING" or "FLOAT" are special values for fields on the node.
  The type can be a list for selection.
  
  Returns: `dict`:
      - Key input_fields_group (`string`): Can be either required, hidden or optional. A node class must have property `required`
      - Value input_fields (`dict`): Contains input fields config:
          * Key field_name (`string`): Name of a entry-point method's argument
          * Value field_config (`tuple`):
              + First value is a string indicate the type of field or a list for selection.
              + Secound value is a config for type "INT", "STRING" or "FLOAT".
  """
  @classmethod
  def INPUT_TYPES(self):
    return {
      'required': {
        'images': ('IMAGE', ),
        'filename_prefix': ('STRING', {'default': 'myFile', 'multiline': False}),
        'filename_keys': ('STRING', {'default': 'sampler_name, scheduler, cfg, steps', 'multiline': True}),
        'foldername_prefix': ('STRING', {'default': 'saveExtended/', 'multiline': False}),
        'foldername_keys': ('STRING', {'default': 'ckpt_name, ./exampleSubfolder', 'multiline': True}),
        'delimiter': ('STRING', {'default': '_', 'multiline': False}),
        'save_job_data': (['disabled', 'prompt', 'basic, prompt', 'basic, sampler, prompt', 'basic, models, sampler, prompt'],{'default': 'basic, models, sampler, prompt'}),
        'job_data_per_image': ([False, True], {'default': False}),
        'job_custom_text': ('STRING', {'default': '', 'multiline': False}),
        'save_metadata': ([True, False], {'default': True}),
        'counter_digits': ("INT", {
          "default": 4, 
          "min": 1, 
          "max": 8, 
          "step": 1,
          "display": "silder"
         }),
        'counter_position': (['last', 'first'], {'default': 'last'}),
        'one_counter_per_folder': ([True, False], {'default': True}),
        'image_preview': ([True, False], {'default': True}),
        'output_ext': (['.png'], {'default': '.png'}),
      },
      'optional': {
        'positive_text_opt': ('STRING', {'forceInput': True}),
        'negative_text_opt': ('STRING', {'forceInput': True}),
                    },
      'hidden': {'prompt': 'PROMPT', 'extra_pnginfo': 'EXTRA_PNGINFO'},
    }
  
  RETURN_TYPES = ()
  FUNCTION = 'save_images'
  OUTPUT_NODE = True
  CATEGORY = 'image'
  
  
  def get_subfolder_path(self, image_path, output_path):
    image_path = Path(image_path).resolve()
    output_path = Path(output_path).resolve()
    relative_path = image_path.relative_to(output_path)
    subfolder_path = relative_path.parent
    
    return str(subfolder_path)
  
  
  # Get current counter number from file names
  def get_latest_counter(self, one_counter_per_folder, folder_path, filename_prefix, counter_digits, counter_position='last', output_ext='.png'):
    counter = 1
    if not os.path.exists(folder_path):
      print(f"SaveImageExtended error: Folder {folder_path} does not exist, starting counter at 1.")
      return counter
    
    try:
      files = [file for file in os.listdir(folder_path) if file.endswith(output_ext)]
      if files:
        if counter_position not in self.counter_position: counter_position = self.counter_position[0]
        if counter_position == 'last':
          # BUG: this works only if extension is 3 letters like png, this will break with webp and avif:
          counters = [int(file[-(4 + counter_digits):-4]) if file[-(4 + counter_digits):-4].isdigit() else 0 for file in files if one_counter_per_folder or file.startswith(filename_prefix)]
        else:
          counters = [int(file[:counter_digits]) if file[:counter_digits].isdigit() else 0 for file in files if one_counter_per_folder or file[counter_digits +1:].startswith(filename_prefix)]
        
        if counters:
          counter = max(counters) + 1
    
    except Exception as e:
      print(f"SaveImageExtended error: An error occurred while finding the latest counter: {e}")
    
    return counter
  
  
  def find_keys_recursively(self, prompt, keys_to_find, found_values):
    for key, value in prompt.items():
      if key in keys_to_find:
        found_values[key] = value
      elif isinstance(value, dict):
        self.find_keys_recursively(value, keys_to_find, found_values)
  
  
  def cleanup_fileName(self, value):
    if isinstance(value, str):
      # takes care of all the possible safetensor extensions under the sun
      value = os.path.splitext(os.path.basename(value))[0]
    return value
  
  
  # this method pretty much does the same as find_keys_recursively, except it's for job.json export
  def find_parameter_values(self, target_keys, prompt, found_values={}):
    loras_string = ''
    for key, value in prompt.items():
      # print(f"debug find_parameter_values: key={key} value={value}")
      if 'loras' in target_keys:
        # Match both formats: lora_xx and lora_name_x
        if re.match(r'lora(_name)?(_\d+)?', key):
          if value is not None:
            value = self.cleanup_fileName(value)
            loras_string += f'{value}, '
      
      # test if value is dict BEFORE cleaning up string value. come on, man...
      if isinstance(value, dict):
        self.find_parameter_values(target_keys, value, found_values)
      
      if key in target_keys:
        value = self.cleanup_fileName(value)
        found_values[key] = value
    
    if 'loras' in target_keys and loras_string:
      found_values['loras'] = loras_string.strip().strip(',')
    
    if len(target_keys) == 1:
      return found_values.get(target_keys[0], None)
    
    return found_values
  
  
  def generate_custom_name(self, keys_to_extract, prefix, delimiter, resolution, prompt):
    custom_name = prefix
    if prompt is not None and len(keys_to_extract) > 0:
      found_values = {}
      # print(f"debug generate_custom_name: --prefix: {prefix}")
      # print(f"debug generate_custom_name: --keys_to_extract: {keys_to_extract}")
      # print(f"debug generate_custom_name: --prompt:")
      # pprint.pprint(prompt)
      
      # now separating numbered keys from non-numbered keys:
      #   37.ckpt_name = i want the ckpt_name from node #37
      #      ckpt_name = i want the ckpt_name from the highest numbered node = the last one found
      # prompt looks like this:
      # {'1': {'class_type': 'KSampler',
      #   'inputs': {'cfg': 1.6, 
      #     'denoise': 1.0, ...
      for key in keys_to_extract:
        node, nodeKey = None, None
        splitKey = key.split('.')
        if len(splitKey) > 1:
          node, nodeKey = splitKey[0], splitKey[1]
          if node in prompt:
            print(f"debug generate_custom_name: --node.nodeKey = {node}.{nodeKey}")
            # splitKey[0] = #node number found in prompt, we will recurse only in that node:
            value = self.find_keys_recursively(prompt[node], [nodeKey], found_values)
          else:
            # if splitKey[0] = #node number not found in prompt, we will just inform the user
            print(f"SaveImageExtended info: node #{node} not found")
        else:
          # from now on we will wotk with nodeKey, that will save us tons of if then else
          nodeKey = key
          # we just try and find the last value for that key, whichever node it's in:
          value = self.find_keys_recursively(prompt, [nodeKey], found_values)
        
        # at this point we have a nodeKey but maybe no value
        # now we analyze each value found and format them accordingly:
        value = found_values[nodeKey]
        print(f"debug generate_custom_name: ----key: {nodeKey}")
        print(f"debug generate_custom_name: ----value: {value}")

        if value is None:
          # key not found = it's a fixed string
          print(f"debug generate_custom_name: ------value=key: {nodeKey}")
          value = nodeKey
        
        if isinstance(value, float):
          value = round(float(value), 1)
        
        # now we build the custom_name:
        if isinstance(value, str):
          value = self.cleanup_fileName(value)
          # prefix and keys can very well be subfolders ending or starting with a /
          if (value.startswith('./') or value.startswith('/') or custom_name.endswith('/')):
            # for subfolders, do not start filename with a delimiter...
            custom_name += f"{value}"
          else:
            custom_name += f"{delimiter}{value}"
        else:
          # could be int or float, can't be anything else
          custom_name += f"{delimiter}{value}"
        # print(f"debug generate_custom_name: ------custom_name: {custom_name}")
    return custom_name.strip(delimiter)
  
  
  def save_job_to_json(self, save_job_data, prompt, filename_prefix, positive_text_opt, negative_text_opt, job_custom_text, resolution, output_path, filename):
    prompt_keys_to_save = {}
    if 'basic' in save_job_data:
      if len(filename_prefix) > 0:
        prompt_keys_to_save['filename_prefix'] = filename_prefix
      prompt_keys_to_save['resolution'] = resolution
    if len(job_custom_text) > 0:
      prompt_keys_to_save['custom_text'] = job_custom_text
    
    if 'models' in save_job_data:
      models = self.find_parameter_values(['ckpt_name', 'loras', 'vae_name', 'model_name'], prompt)
      if models.get('ckpt_name'):
        prompt_keys_to_save['checkpoint'] = models['ckpt_name']
      if models.get('loras'):
        prompt_keys_to_save['loras'] = models['loras']
      if models.get('vae_name'):
        prompt_keys_to_save['vae'] = models['vae_name']
      if models.get('model_name'):
        prompt_keys_to_save['upscale_model'] = models['model_name']
    
    if 'sampler' in save_job_data:
      prompt_keys_to_save['sampler_parameters'] = self.find_parameter_values(['seed', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise'], prompt)
    
    if 'prompt' in save_job_data:
      if positive_text_opt is not None:
        if not (isinstance(positive_text_opt, list) and
            len(positive_text_opt) == 2 and
            isinstance(positive_text_opt[0], str) and
            len(positive_text_opt[0]) < 6 and
            isinstance(positive_text_opt[1], (int, float))):
          prompt_keys_to_save['positive_prompt'] = positive_text_opt
      
      if negative_text_opt is not None:
        if not (isinstance(positive_text_opt, list) and len(negative_text_opt) == 2 and isinstance(negative_text_opt[0], str) and isinstance(negative_text_opt[1], (int, float))):
          prompt_keys_to_save['negative_prompt'] = negative_text_opt
      
      #If no user input for prompts
      if positive_text_opt is None and negative_text_opt is None:
        if prompt is not None:
          for key in prompt:
            class_type = prompt[key].get('class_type', None)
            inputs = prompt[key].get('inputs', {})
            
            # Efficiency Loaders prompt structure
            if class_type == 'Efficient Loader' or class_type == 'Eff. Loader SDXL':
              if 'positive' in inputs and 'negative' in inputs:
                prompt_keys_to_save['positive_prompt'] = inputs.get('positive')
                prompt_keys_to_save['negative_prompt'] = inputs.get('negative')
            
            # KSampler/UltimateSDUpscale prompt structure
            elif class_type == 'KSampler' or class_type == 'KSamplerAdvanced' or class_type == 'UltimateSDUpscale':
              positive_ref = inputs.get('positive', [])[0] if 'positive' in inputs else None
              negative_ref = inputs.get('negative', [])[0] if 'negative' in inputs else None
              
              positive_text = prompt.get(str(positive_ref), {}).get('inputs', {}).get('text', None)
              negative_text = prompt.get(str(negative_ref), {}).get('inputs', {}).get('text', None)
              
              # If we get non text inputs
              if positive_text is not None:
                if isinstance(positive_text, list):
                  if len(positive_text) == 2:
                    if isinstance(positive_text[0], str) and len(positive_text[0]) < 6:
                      if isinstance(positive_text[1], (int, float)):
                        continue
                prompt_keys_to_save['positive_prompt'] = positive_text
              
              if negative_text is not None:
                if isinstance(negative_text, list):
                  if len(negative_text) == 2:
                    if isinstance(negative_text[0], str) and len(negative_text[0]) < 6:
                      if isinstance(negative_text[1], (int, float)):
                        continue
                prompt_keys_to_save['positive_prompt'] = negative_text
    
    # Append data and save
    json_file_path = os.path.join(output_path, filename)
    existing_data = {}
    if os.path.exists(json_file_path):
      try:
        with open(json_file_path, 'r') as f:
          existing_data = json.load(f)
      except json.JSONDecodeError:
        print(f"SaveImageExtended error: The file {json_file_path} is empty or malformed. Initializing with empty data.")
        existing_data = {}
    
    timestamp = datetime.now().strftime('%c')
    new_entry = {}
    new_entry[timestamp] = prompt_keys_to_save
    existing_data.update(new_entry)
    
    with open(json_file_path, 'w') as f:
      json.dump(existing_data, f, indent=4)

# class SaveImageExtended -------------------------------------------------------------------------------


  def save_images(self,
      counter_digits,
      counter_position,
      one_counter_per_folder,
      delimiter,
      filename_keys,
      foldername_keys,
      images,
      image_preview,
      save_job_data,
      job_data_per_image,
      job_custom_text,
      save_metadata,
      filename_prefix='myFile',
      foldername_prefix='saveExtended/',
      extra_pnginfo=None,
      negative_text_opt=None,
      positive_text_opt=None,
      prompt=None,
      output_ext='.png'
    ):
    
    # Get set resolution value
    i = 255. * images[0].cpu().numpy()
    img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
    resolution = f'{img.width}x{img.height}'
    
    delimiter = delimiter[0]
    filename_keys_to_extract = [item.strip() for item in filename_keys.split(',')]
    foldername_keys_to_extract = [item.strip() for item in foldername_keys.split(',')]
    custom_filename = self.generate_custom_name(filename_keys_to_extract, filename_prefix, delimiter, resolution, prompt)
    custom_foldername = self.generate_custom_name(foldername_keys_to_extract, foldername_prefix, delimiter, resolution, prompt)
    
    # Create folders, count images, save images
    try:
      full_output_folder, filename, _, _, custom_filename = folder_paths.get_save_image_path(custom_filename, self.output_dir, images[0].shape[1], images[0].shape[0])
      output_path = os.path.join(full_output_folder, custom_foldername)
      # print(f"debug save_images: full_output_folder={full_output_folder}")
      # print(f"debug save_images: custom_foldername={custom_foldername}")
      # print(f"debug save_images: output_path={output_path}")
      os.makedirs(output_path, exist_ok=True)
      counter = self.get_latest_counter(one_counter_per_folder, output_path, filename, counter_digits, counter_position, output_ext)
      # print(f"debug save_images: counter={counter}")
    
      results = list()
      for image in images:
        i = 255. * image.cpu().numpy()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
        metadata = None
        if save_metadata:
          metadata = PngInfo()
          if prompt is not None:
            metadata.add_text('prompt', json.dumps(prompt))
          if extra_pnginfo is not None:
            for x in extra_pnginfo:
              metadata.add_text(x, json.dumps(extra_pnginfo[x]))
        
        if counter_position == 'last':
          file = f'{filename}{delimiter}{counter:0{counter_digits}}{output_ext}'
        else:
          file = f'{counter:0{counter_digits}}{delimiter}{filename}{output_ext}'
        
        image_path = os.path.join(output_path, file)
        # print(f"debug save_images: image_path={image_path}")
        img.save(image_path, pnginfo=metadata, compress_level=self.png_compress_level)
        
        if save_job_data != 'disabled' and job_data_per_image:
          self.save_job_to_json(save_job_data, prompt, filename_prefix, positive_text_opt, negative_text_opt, job_custom_text, resolution, output_path, f'{file.removesuffix(output_ext)}.json')
        
        subfolder = self.get_subfolder_path(image_path, self.output_dir)
        results.append({ 'filename': file, 'subfolder': subfolder, 'type': self.type})
        counter += 1
      
      if save_job_data != 'disabled' and not job_data_per_image:
        self.save_job_to_json(save_job_data, prompt, filename_prefix, positive_text_opt, negative_text_opt, job_custom_text, resolution, output_path, 'jobs.json')
    
    except OSError as e:
      print(f"SaveImageExtended error: An error occurred while creating the subfolder or saving the image: {e}")
    else:
      if not image_preview:
        results = list()
      return { 'ui': { 'images': results } }


NODE_CLASS_MAPPINGS = {
  'SaveImageExtended': SaveImageExtended,
}


NODE_DISPLAY_NAME_MAPPINGS = {
  'SaveImageExtended': 'Save Image Extended',
}


# {'1': {'class_type': 'KSampler',
       # 'inputs': {'cfg': 1.6,
                  # 'denoise': 1.0,
                  # 'latent_image': ['6', 0],
                  # 'model': ['2', 0],
                  # 'negative': ['5', 0],
                  # 'positive': ['4', 0],
                  # 'sampler_name': 'lcm',
                  # 'scheduler': 'sgm_uniform',
                  # 'seed': 233248937945750,
                  # 'steps': 4}},
 # '12': {'class_type': 'KSampler',
        # 'inputs': {'cfg': 1.6,
                   # 'denoise': 0.22,
                   # 'model': ['2', 0],
                   # 'negative': ['5', 0],
                   # 'positive': ['4', 0],
                   # 'sampler_name': 'lcm',
                   # 'scheduler': 'sgm_uniform',
                   # 'seed': 697295967325855,
                   # 'steps': 4}},
 # '13': {'class_type': 'VAEDecode',
        # 'inputs': {'samples': ['23', 0], 'vae': ['3', 2]}},
 # '2': {'class_type': 'LoraLoader',
       # 'inputs': {'clip': ['9', 1],
                  # 'lora_name': 'lcm\\SD1.5\\pytorch_lora_weights.safetensors',
                  # 'model': ['9', 0],
                  # 'strength_clip': 1.0,
                  # 'strength_model': 1.0}},
 # '23': {'class_type': 'KSampler',
        # 'inputs': {'cfg': 1.6,
                   # 'denoise': 0.1,
                   # 'latent_image': ['45', 0],
                   # 'model': ['2', 0],
                   # 'negative': ['5', 0],
                   # 'positive': ['4', 0],
                   # 'sampler_name': 'lcm',
                   # 'scheduler': 'sgm_uniform',
                   # 'seed': 697295967325855,
                   # 'steps': 4}},
 # '25': {'class_type': 'VAEDecode',
        # 'inputs': {'samples': ['12', 0], 'vae': ['3', 2]}},
 # '3': {'class_type': 'CheckpointLoaderSimple',
       # 'inputs': {'ckpt_name': 'epicrealism_naturalSinRC1VAE.safetensors'}},
 # '35': {'class_type': 'SaveImageExtended',
        # 'inputs': {'counter_digits': 4,
                   # 'counter_position': 'last',
                   # 'delimiter': '-',
                   # 'filename_keys': 'sampler_name, scheduler, cfg, steps, '
                                    # 'upscale2',
                   # 'filename_prefix': 'LCM',
                   # 'foldername_keys': 'ckpt_name, ./upscale',
                   # 'foldername_prefix': 'LCM-LoRA-basic/',
                   # 'image_preview': True,
                   # 'images': ['13', 0],
                   # 'job_custom_text': '',
                   # 'job_data_per_image': False,
                   # 'one_counter_per_folder': True,
                   # 'output_ext': '.png',
                   # 'save_job_data': 'basic, models, sampler, prompt',
                   # 'save_metadata': True}},
 # '36': {'class_type': 'SaveImageExtended',
        # 'inputs': {'counter_digits': 4,
                   # 'counter_position': 'last',
                   # 'delimiter': '-',
                   # 'filename_keys': 'sampler_name, scheduler, cfg, steps',
                   # 'filename_prefix': 'LCM',
                   # 'foldername_keys': 'ckpt_name',
                   # 'foldername_prefix': 'LCM-LoRA-basic/',
                   # 'image_preview': True,
                   # 'images': ['7', 0],
                   # 'job_custom_text': '',
                   # 'job_data_per_image': False,
                   # 'one_counter_per_folder': True,
                   # 'output_ext': '.png',
                   # 'save_job_data': 'basic, models, sampler, prompt',
                   # 'save_metadata': True}},
 # '37': {'class_type': 'SaveImageExtended',
        # 'inputs': {'counter_digits': 4,
                   # 'counter_position': 'last',
                   # 'delimiter': '-',
                   # 'filename_keys': 'sampler_name, scheduler, cfg, steps, '
                                    # 'upscale1',
                   # 'filename_prefix': 'LCM',
                   # 'foldername_keys': 'ckpt_name, ./upscale',
                   # 'foldername_prefix': 'LCM-LoRA-basic/',
                   # 'image_preview': False,
                   # 'images': ['25', 0],
                   # 'job_custom_text': '',
                   # 'job_data_per_image': False,
                   # 'one_counter_per_folder': True,
                   # 'output_ext': '.png',
                   # 'save_job_data': 'basic, models, sampler, prompt',
                   # 'save_metadata': True}},
 # '4': {'class_type': 'CLIPTextEncode',
       # 'inputs': {'clip': ['3', 1],
                  # 'text': 'portrait of an old man, hires, masterpiece, full '
                          # 'body, cinematic lighting'}},
 # '45': {'class_type': 'ttN hiresfixScale',
        # 'inputs': {'crop': 'disabled',
                   # 'height': 1024,
                   # 'image': ['25', 0],
                   # 'image_output': 'Hide',
                   # 'longer_side': 1024,
                   # 'model_name': '4x-UltraSharp.pth',
                   # 'output_latent': True,
                   # 'percent': 40,
                   # 'rescale': 'by percentage',
                   # 'rescale_after_model': True,
                   # 'rescale_method': 'nearest-exact',
                   # 'save_prefix': 'ComfyUI',
                   # 'vae': ['3', 2],
                   # 'width': 1024}},
 # '48': {'class_type': 'UpscaleModelLoader',
        # 'inputs': {'model_name': '001_classicalSR_DF2K_s64w8_SwinIR-M_x4.pth'}},
 # '5': {'class_type': 'CLIPTextEncode',
       # 'inputs': {'clip': ['3', 1], 'text': 'lowres, worst quality'}},
 # '6': {'class_type': 'EmptyLatentImage',
       # 'inputs': {'batch_size': 1, 'height': 512, 'width': 512}},
 # '7': {'class_type': 'VAEDecode',
       # 'inputs': {'samples': ['1', 0], 'vae': ['3', 2]}},
 # '9': {'class_type': 'LoraLoader',
       # 'inputs': {'clip': ['3', 1],
                  # 'lora_name': 'epiCRealismHelper.safetensors',
                  # 'model': ['3', 0],
                  # 'strength_clip': 1.0,
                  # 'strength_model': 0.6}}}