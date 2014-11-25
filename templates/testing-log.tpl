% include('templates/header.tpl', title='Series')

<ul class="nav nav-tabs">
    <li role="presentation"><a href="/series/{{series['message-id']}}">Thread</a></li>
    <li role="presentation" class="active"><a href="#">Testing</a></li>
</ul>
<br>


<h3>
    %if series.get('merged'):
        <span class="label label-primary">Merged</span>
    %elif series['testing-passed']:
        <span class="label label-success">Passed</span>
    %else:
        <span class="label label-danger">Failed</span>
    %end
</h3>
<br>
<pre>{{log}}</pre>

% include('templates/footer.tpl')
