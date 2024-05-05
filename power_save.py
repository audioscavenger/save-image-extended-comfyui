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

# class PowerSave -------------------------------------------------------------------------------
class PowerSave:
  def __init__(self):
    self.output_dir = folder_paths.get_output_directory()
    self.type = 'output'
    self.prefix_append = ''
  
  @classmethod
  def INPUT_TYPES(s):
    return {
      'required': {
        'images': ('IMAGE', ),
        'output_ext': (['.png', '.webp'], {'default': '.png'}),
        'filename_prefix': ('STRING', {'default': 'myFile'}),
        'filename_keys': ('STRING', {'default': 'sampler_name, scheduler, cfg, steps', 'multiline': False}),
        'foldername_prefix': ('STRING', {'default': 'myFolder/'}),
        'foldername_keys': ('STRING', {'default': 'ckpt_name, ./exampleSubfolder', 'multiline': False}),
        'delimiter': ('STRING', {'default': '-'}),
        'save_job_data': (['disabled', 'prompt', 'basic, prompt', 'basic, sampler, prompt', 'basic, models, sampler, prompt'],{'default': 'basic, prompt'}),
        'job_data_per_image': (['disabled', 'enabled'],{'default': 'disabled'}),
        'job_custom_text': ('STRING', {'default': '', 'multiline': False}),
        'save_metadata': (['disabled', 'enabled'], {'default': 'enabled'}),
        'counter_digits': ('STRING', {'default': 4}),
        'counter_position': (['first', 'last'], {'default': 'last'}),
        'one_counter_per_folder': (['disabled', 'enabled'], {'default': 'disabled'}),
        'image_preview': (['disabled', 'enabled'], {'default': 'enabled'}),
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
  def get_latest_counter(self, one_counter_per_folder, folder_path, filename_prefix, counter_digits, counter_position='last'):
    counter = 1
    if not os.path.exists(folder_path):
      print(f"Folder {folder_path} does not exist, starting counter at 1.")
      return counter
    
    try:
      files = [f for f in os.listdir(folder_path) if f.endswith(output_ext)]
      if files:
        if counter_position == 'last':
          counters = [int(f[-(4 + counter_digits):-4]) if f[-(4 + counter_digits):-4].isdigit() else 0 for f in files if one_counter_per_folder == 'enabled' or f.startswith(filename_prefix)]
        elif counter_position == 'first':
          counters = [int(f[:counter_digits]) if f[:counter_digits].isdigit() else 0 for f in files if one_counter_per_folder == 'enabled' or f[counter_digits +1:].startswith(filename_prefix)]
        else:
          print(f"Invalid counter_position. Using 'last' as default.")
          counters = [int(f[-(4 + counter_digits):-4]) if f[-(4 + counter_digits):-4].isdigit() else 0 for f in files if one_counter_per_folder == 'enabled' or f.startswith(filename_prefix)]
        
        if counters:
          counter = max(counters) + 1
    
    except Exception as e:
      print(f"An error occurred while finding the latest counter: {e}")
    
    return counter
  
  @staticmethod
  def find_keys_recursively(d, keys_to_find, found_values):
    for key, value in d.items():
      if key in keys_to_find:
        found_values[key] = value
      if isinstance(value, dict):
        PowerSave.find_keys_recursively(value, keys_to_find, found_values)
  
  @staticmethod
  def remove_file_extension(value):
    if isinstance(value, str):
      value = value.removesuffix('.safetensors')
      value = value.removesuffix('.ckpt')
      value = value.removesuffix('.pt')
    
    return value
  
  @staticmethod
  def find_parameter_values(target_keys, obj, found_values=None):
    if found_values is None:
      found_values = {}
    
    if not isinstance(target_keys, list):
      target_keys = [target_keys]
    
    loras_string = ''
    for key, value in obj.items():
      # print(f"debug find_parameter_values: key={key} value={value}")
      if 'loras' in target_keys:
        # Match both formats: lora_xx and lora_name_x
        if re.match(r'lora(_name)?(_\d+)?', key):
          if value is not None:
            value = PowerSave.remove_file_extension(value)
            loras_string += f'{value}, '
      
      # test if value is dict BEFORE cleaning up string value. come on, man...
      if isinstance(value, dict):
        PowerSave.find_parameter_values(target_keys, value, found_values)
      
      if key in target_keys:
        value = PowerSave.remove_file_extension(value)
        found_values[key] = value
    
    if 'loras' in target_keys and loras_string:
      found_values['loras'] = loras_string.strip().strip(',')
    
    if len(target_keys) == 1:
      return found_values.get(target_keys[0], None)
    
    return found_values
  
  
  @staticmethod
  def generate_custom_name(keys_to_extract, prefix, delimiter, resolution, prompt):
    custom_name = prefix
    if prompt is not None and len(keys_to_extract) > 0:
      found_values = {'resolution': resolution}
      print(f"debug generate_custom_name: --keys_to_extract: {keys_to_extract}")
      PowerSave.find_keys_recursively(prompt, keys_to_extract, found_values)
      for key in keys_to_extract:
        value = found_values.get(key)
        print(f"debug generate_custom_name: ----key: {key}")
        print(f"debug generate_custom_name: ----value: {value}")
        if value is not None:
          if key == 'cfg' or key =='denoise':
            try:
              value = round(float(value), 1)
            except ValueError:
              pass
        else:
          # you can certainly add fixed strings as delimiters! Adding unknown key will make it a delimiter:
          print(f"debug generate_custom_name: ------value=key: {key}")
          value = key
        
        if (isinstance(value, str)):
          value = PowerSave.remove_file_extension(value)
          # prefix and keys can very well be subfolders ending or starting with a /
          # print(f"debug generate_custom_name: ------value0=: {value}")
          if (value.startswith('./') or value.startswith('/') or custom_name.endswith('/')):
            # for subfolders, do not start filename with a delimiter...
            custom_name += f"{value}"
          else:
            custom_name += f"{delimiter}{value}"
          print(f"debug generate_custom_name: ------custom_name: {custom_name}")
    return custom_name.strip(delimiter)
  
  
  @staticmethod
  def save_job_to_json(save_job_data, prompt, filename_prefix, positive_text_opt, negative_text_opt, job_custom_text, resolution, output_path, filename):
    prompt_keys_to_save = {}
    if 'basic' in save_job_data:
      if len(filename_prefix) > 0:
        prompt_keys_to_save['filename_prefix'] = filename_prefix
      prompt_keys_to_save['resolution'] = resolution
    if len(job_custom_text) > 0:
      prompt_keys_to_save['custom_text'] = job_custom_text
    
    if 'models' in save_job_data:
      models = PowerSave.find_parameter_values(['ckpt_name', 'loras', 'vae_name', 'model_name'], prompt)
      if models.get('ckpt_name'):
        prompt_keys_to_save['checkpoint'] = models['ckpt_name']
      if models.get('loras'):
        prompt_keys_to_save['loras'] = models['loras']
      if models.get('vae_name'):
        prompt_keys_to_save['vae'] = models['vae_name']
      if models.get('model_name'):
        prompt_keys_to_save['upscale_model'] = models['model_name']
    
    if 'sampler' in save_job_data:
      prompt_keys_to_save['sampler_parameters'] = PowerSave.find_parameter_values(['seed', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise'], prompt)
    
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
        print(f"The file {json_file_path} is empty or malformed. Initializing with empty data.")
        existing_data = {}
    
    timestamp = datetime.now().strftime('%c')
    new_entry = {}
    new_entry[timestamp] = prompt_keys_to_save
    existing_data.update(new_entry)
    
    with open(json_file_path, 'w') as f:
      json.dump(existing_data, f, indent=4)

# class PowerSave -------------------------------------------------------------------------------


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
      filename_prefix='',
      foldername_prefix='',
      extra_pnginfo=None,
      negative_text_opt=None,
      positive_text_opt=None,
      prompt=None
    ):
    
    # Get set resolution value
    i = 255. * images[0].cpu().numpy()
    img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
    resolution = f'{img.width}x{img.height}'
    
    filename_keys_to_extract = [item.strip() for item in filename_keys.split(',')]
    foldername_keys_to_extract = [item.strip() for item in foldername_keys.split(',')]
    custom_filename = PowerSave.generate_custom_name(filename_keys_to_extract, filename_prefix, delimiter, resolution, prompt)
    custom_foldername = PowerSave.generate_custom_name(foldername_keys_to_extract, foldername_prefix, delimiter, resolution, prompt)
    
    # Create and save images
    try:
      full_output_folder, filename, _, _, custom_filename = folder_paths.get_save_image_path(custom_filename, self.output_dir, images[0].shape[1], images[0].shape[0])
      output_path = os.path.join(full_output_folder, custom_foldername)
      print(f"debug save_images: full_output_folder={full_output_folder}")
      print(f"debug save_images: custom_foldername={custom_foldername}")
      print(f"debug save_images: output_path={output_path}")
      os.makedirs(output_path, exist_ok=True)
      counter = self.get_latest_counter(one_counter_per_folder, output_path, filename, counter_digits, counter_position)

      results = list()
      for image in images:
        i = 255. * image.cpu().numpy()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
        metadata = None
        if save_metadata == 'enabled':
          metadata = PngInfo()
          if prompt is not None:
            metadata.add_text('prompt', json.dumps(prompt))
          if extra_pnginfo is not None:
            for x in extra_pnginfo:
              metadata.add_text(x, json.dumps(extra_pnginfo[x]))
        
        if counter_position == 'last':
          file = f'{filename}{delimiter}{counter:0{counter_digits}}'+output_ext
        else:
          file = f'{counter:0{counter_digits}}{delimiter}{filename}'+output_ext
        
        image_path = os.path.join(output_path, file)
        img.save(image_path, pnginfo=metadata, compress_level=4)
        
        if save_job_data != 'disabled' and job_data_per_image =='enabled':
          PowerSave.save_job_to_json(save_job_data, prompt, filename_prefix, positive_text_opt, negative_text_opt, job_custom_text, resolution, output_path, f'{file.removesuffix(output_ext)}.json')
        
        subfolder = self.get_subfolder_path(image_path, self.output_dir)
        results.append({ 'filename': file, 'subfolder': subfolder, 'type': self.type})
        counter += 1
      
      if save_job_data != 'disabled' and job_data_per_image =='disabled':
        PowerSave.save_job_to_json(save_job_data, prompt, filename_prefix, positive_text_opt, negative_text_opt, job_custom_text, resolution, output_path, 'jobs.json')
    
    except OSError as e:
      print(f'An error occurred while creating the subfolder or saving the image: {e}')
    else:
      if image_preview == 'disabled':
        results = list()
      return { 'ui': { 'images': results } }


NODE_CLASS_MAPPINGS = {
  'PowerSave': PowerSave,
}


NODE_DISPLAY_NAME_MAPPINGS = {
  'PowerSave': 'Power Save',
}
